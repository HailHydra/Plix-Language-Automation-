import os
import sys
import json
import time
import requests
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.common import load_env
from src.synclabs_client import SyncLabsClient
from src.dub_assembly import assemble_segment, join_segments
from src.scene_analyzer import get_video_info

load_env(".env")

ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY")
SYNC_KEY = os.environ.get("SYNC_API_KEY")

def ensure_voice_clone(audio_sample_path, voice_name="Dr_Priyanta_True_Voice"):
    headers = {"xi-api-key": ELEVEN_KEY}
    r = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers)
    if r.ok:
        voices = r.json().get("voices", [])
        matched = next((v for v in voices if v["name"] == voice_name), None)
        if matched:
            print(f"Using existing voice '{voice_name}' (ID: {matched['voice_id']})")
            return matched["voice_id"]

    print(f"Creating new voice clone '{voice_name}' from {audio_sample_path}...")
    with open(audio_sample_path, "rb") as f:
        files = {"files": ("creator_sample.wav", f, "audio/wav")}
        data = {"name": voice_name, "description": "High fidelity creator clone for 100% uniform video dubbing"}
        resp = requests.post("https://api.elevenlabs.io/v1/voices/add", headers=headers, data=data, files=files)
        if not resp.ok:
            raise RuntimeError(f"ElevenLabs voice clone error: {resp.status_code} {resp.text}")
        voice_id = resp.json()["voice_id"]
        print(f"Created voice ID: {voice_id}")
        return voice_id

def generate_tts(voice_id, text, output_path):
    headers = {"xi-api-key": ELEVEN_KEY}
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.85,
            "style": 0.0,
            "use_speaker_boost": True
        }
    }
    resp = requests.post(url, headers=headers, json=payload)
    if not resp.ok:
        raise RuntimeError(f"ElevenLabs TTS error: {resp.status_code} {resp.text}")
    with open(output_path, "wb") as f:
        f.write(resp.content)
    print(f"Generated TTS ({len(resp.content)} bytes) -> {output_path.name}")
    return output_path

def time_fit_audio(input_audio, output_audio, target_duration, delay_ms=0):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(input_audio)],
        capture_output=True, text=True
    )
    raw_duration = float(probe.stdout.strip())
    speech_duration = target_duration - (delay_ms / 1000.0)
    tempo = raw_duration / speech_duration
    
    # Bound tempo factor safely
    tempo = max(0.5, min(2.0, tempo))
    
    af_filters = [f"atempo={tempo:.4f}"]
    if delay_ms > 0:
        af_filters.append(f"adelay={delay_ms}|{delay_ms}")
    af_filters.append(f"apad=whole_dur={target_duration:.4f}")

    cmd = [
        "ffmpeg", "-y", "-i", str(input_audio),
        "-af", ",".join(af_filters),
        "-t", f"{target_duration:.4f}",
        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(output_audio)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_audio

def sync_talking_head(client, video_path, audio_path, output_path, model="lipsync-2-pro"):
    print(f"Uploading {video_path.name} & {audio_path.name} to Sync Labs...")
    video_url = client.upload_file(video_path, content_type="video/mp4")
    audio_url = client.upload_file(audio_path, content_type="audio/wav")
    print(f"Triggering lip-sync generation ({model})...")
    gen_data = client.generate(video_url, audio_url, model=model)
    gen_id = gen_data["id"]
    print(f"Waiting for generation {gen_id}...")
    res = client.wait_for_completion(gen_id, poll_interval=6)
    out_url = res["outputUrl"]
    print(f"Downloading result to {output_path}...")
    client.download_result(out_url, output_path)
    return output_path

def main():
    base_dir = Path(r"output\dub_WhatsApp Video 2026-09-28 at 6.01.20 PM_en")
    source_video = Path(r"input\WhatsApp Video 2026-09-28 at 6.01.20 PM.mp4")
    orig_sample = base_dir / "orig_source_audio.wav"
    seg_dir = base_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    # 1. Ensure Voice Clone from original creator voice
    voice_id = ensure_voice_clone(orig_sample, "Dr_Priyanta_True_Voice")

    # 2. Complete Script with exact segment boundaries
    # Segment 0..3: 0.000s - 5.589s (duration 5.589s)
    # Segment 4: 5.589s - 9.343s (duration 3.754s) -> Talking Head (Plix Jamun Acne Marks Combo)
    # Segment 5..8: 9.343s - 13.096s (duration 3.753s) -> B-roll (Niacinamide, Salicylic Acid, Zinc)
    # Segment 9..10: 13.096s - 16.183s (duration 3.087s) -> B-roll + Talking Head (exfoliate, 14 days)
    # Segment 11..12: 16.183s - 20.270s (duration 4.087s) -> Talking Head (fade, bright & even)
    # Segment 13..14: 20.270s - 22.606s (duration 2.336s) -> CTA (skincare routine now!)

    scripts = [
        {
            "id": "hook",
            "text": "Fairies aren't gonna come and make your skin glow while you sleep. Your skin doesn't just get better overnight.",
            "duration": 5.589,
            "delay_ms": 160
        },
        {
            "id": "seg4",
            "text": "If you've got dark spots, just start using Plix's Jamun Acne Marks Combo. It's",
            "duration": 3.754,
            "delay_ms": 50
        },
        {
            "id": "seg5_8",
            "text": "got Niacinamide, Salicylic Acid, and Zinc, which reduce inflammation,",
            "duration": 3.753,
            "delay_ms": 50
        },
        {
            "id": "seg9_10",
            "text": "exfoliate the skin, and even prevent breakouts. In just 14 days, dark spots",
            "duration": 3.087,
            "delay_ms": 50
        },
        {
            "id": "seg11_12",
            "text": "will fade and your skin will look bright and even. It's that simple, so start your",
            "duration": 4.087,
            "delay_ms": 50
        },
        {
            "id": "seg13_14",
            "text": "skincare routine now!",
            "duration": 2.336,
            "delay_ms": 50
        }
    ]

    print("\n--- STEP 1: Generating 100% Uniform TTS Audio for All Segments ---")
    generated_audio = {}
    for item in scripts:
        raw_mp3 = seg_dir / f"uniform_{item['id']}_raw.mp3"
        fitted_wav = seg_dir / f"uniform_{item['id']}_fitted.wav"
        generate_tts(voice_id, item["text"], raw_mp3)
        time_fit_audio(raw_mp3, fitted_wav, item["duration"], item["delay_ms"])
        generated_audio[item["id"]] = fitted_wav
        print(f"  Fitted {item['id']} to {item['duration']:.3f}s -> {fitted_wav.name}")

    print("\n--- STEP 2: Lip-Syncing Talking Head Segments with Sync Labs lipsync-2-pro ---")
    synclabs = SyncLabsClient(default_model="lipsync-2-pro")
    
    # Segment 4 (5.589s - 9.343s) is talking head:
    seg4_raw_video = seg_dir / "seg_004_raw.mp4"
    if not seg4_raw_video.exists():
        subprocess.run(["ffmpeg", "-y", "-ss", "5.589", "-t", "3.754", "-i", str(source_video), "-c", "copy", str(seg4_raw_video)], check=True)

    print("Syncing Segment 4 talking head with uniform audio...")
    seg4_synced = seg_dir / "u_seg_004_synced.mp4"
    sync_talking_head(synclabs, seg4_raw_video, generated_audio["seg4"], seg4_synced)
    print(f"Segment 4 Synced: {seg4_synced}")

    fps = 23.976023976023978
    total_frames = 542

    print("\n--- STEP 3: Assembling Master Video with Dub Assembly ---")
    assembled = []
    # Seg 0 (4 frames)
    s0_raw = seg_dir / "seg_000_raw.mp4"
    if not s0_raw.exists(): subprocess.run(["ffmpeg", "-y", "-ss", "0.0", "-t", "0.1668", "-i", str(source_video), "-c", "copy", str(s0_raw)], check=True)
    assembled.append(assemble_segment(s0_raw, generated_audio["hook"], seg_dir / "u_seg_000.mov", 4, fps, audio_start=0.0))

    # Seg 1 (46 frames)
    s1_raw = seg_dir / "seg_001_raw.mp4"
    if not s1_raw.exists(): subprocess.run(["ffmpeg", "-y", "-ss", "0.1668", "-t", "1.9186", "-i", str(source_video), "-c", "copy", str(s1_raw)], check=True)
    assembled.append(assemble_segment(s1_raw, generated_audio["hook"], seg_dir / "u_seg_001.mov", 46, fps, audio_start=4 / fps))

    # Seg 2 (46 frames)
    s2_raw = seg_dir / "seg_002_raw.mp4"
    if not s2_raw.exists(): subprocess.run(["ffmpeg", "-y", "-ss", "2.0854", "-t", "1.9186", "-i", str(source_video), "-c", "copy", str(s2_raw)], check=True)
    assembled.append(assemble_segment(s2_raw, generated_audio["hook"], seg_dir / "u_seg_002.mov", 46, fps, audio_start=50 / fps))

    # Seg 3 (38 frames)
    s3_raw = seg_dir / "seg_003_raw.mp4"
    if not s3_raw.exists(): subprocess.run(["ffmpeg", "-y", "-ss", "4.0040", "-t", "1.5849", "-i", str(source_video), "-c", "copy", str(s3_raw)], check=True)
    assembled.append(assemble_segment(s3_raw, generated_audio["hook"], seg_dir / "u_seg_003.mov", 38, fps, audio_start=96 / fps))

    # Seg 4 (90 frames) - Talking Head
    assembled.append(assemble_segment(seg4_synced, seg4_synced, seg_dir / "u_seg_004.mov", 90, fps, audio_start=0.0))

    # Seg 5 (30 frames: 9.343 - 10.594 = 1.251s)
    s5_raw = seg_dir / "seg_005_raw.mp4"
    assembled.append(assemble_segment(s5_raw, generated_audio["seg5_8"], seg_dir / "u_seg_005.mov", 30, fps, audio_start=0.0))

    # Seg 6 (18 frames: 10.594 - 11.345 = 0.751s)
    s6_raw = seg_dir / "seg_006_raw.mp4"
    assembled.append(assemble_segment(s6_raw, generated_audio["seg5_8"], seg_dir / "u_seg_006.mov", 18, fps, audio_start=30 / fps))

    # Seg 7 (20 frames: 11.345 - 12.179 = 0.834s)
    s7_raw = seg_dir / "seg_007_raw.mp4"
    assembled.append(assemble_segment(s7_raw, generated_audio["seg5_8"], seg_dir / "u_seg_007.mov", 20, fps, audio_start=48 / fps))

    # Seg 8 (22 frames: 12.179 - 13.096 = 0.917s)
    s8_raw = seg_dir / "seg_008_raw.mp4"
    assembled.append(assemble_segment(s8_raw, generated_audio["seg5_8"], seg_dir / "u_seg_008.mov", 22, fps, audio_start=68 / fps))

    # Seg 9 (22 frames: 13.096 - 14.014 = 0.918s) - B-roll
    s9_raw = seg_dir / "seg_009_raw.mp4"
    assembled.append(assemble_segment(s9_raw, generated_audio["seg9_10"], seg_dir / "u_seg_009.mov", 22, fps, audio_start=0.0))

    # Seg 10 (52 frames: 14.014 - 16.183 = 2.169s) - Talking Head
    seg10_audio_slice = seg_dir / "seg10_uniform_slice.wav"
    subprocess.run(["ffmpeg", "-y", "-ss", f"{22/fps:.4f}", "-t", f"{52/fps:.4f}", "-i", str(generated_audio["seg9_10"]), "-c", "copy", str(seg10_audio_slice)], check=True, capture_output=True)
    s10_raw = seg_dir / "seg_010_raw.mp4"
    print("Syncing Segment 10 talking head with uniform audio...")
    seg10_synced = seg_dir / "u_seg_010_synced.mp4"
    sync_talking_head(synclabs, s10_raw, seg10_audio_slice, seg10_synced)
    assembled.append(assemble_segment(seg10_synced, seg10_synced, seg_dir / "u_seg_010.mov", 52, fps, audio_start=0.0))

    # Seg 11 (50 frames: 16.183 - 18.268 = 2.085s) - Talking Head
    seg11_audio_slice = seg_dir / "seg11_uniform_slice.wav"
    subprocess.run(["ffmpeg", "-y", "-ss", "0.0", "-t", f"{50/fps:.4f}", "-i", str(generated_audio["seg11_12"]), "-c", "copy", str(seg11_audio_slice)], check=True, capture_output=True)
    s11_raw = seg_dir / "seg_011_raw.mp4"
    print("Syncing Segment 11 talking head with uniform audio...")
    seg11_synced = seg_dir / "u_seg_011_synced.mp4"
    sync_talking_head(synclabs, s11_raw, seg11_audio_slice, seg11_synced)
    assembled.append(assemble_segment(seg11_synced, seg11_synced, seg_dir / "u_seg_011.mov", 50, fps, audio_start=0.0))

    # Seg 12 (48 frames: 18.268 - 20.270 = 2.002s) - Talking Head
    seg12_audio_slice = seg_dir / "seg12_uniform_slice.wav"
    subprocess.run(["ffmpeg", "-y", "-ss", f"{50/fps:.4f}", "-t", f"{48/fps:.4f}", "-i", str(generated_audio["seg11_12"]), "-c", "copy", str(seg12_audio_slice)], check=True, capture_output=True)
    s12_raw = seg_dir / "seg_012_raw.mp4"
    print("Syncing Segment 12 talking head with uniform audio...")
    seg12_synced = seg_dir / "u_seg_012_synced.mp4"
    sync_talking_head(synclabs, s12_raw, seg12_audio_slice, seg12_synced)
    assembled.append(assemble_segment(seg12_synced, seg12_synced, seg_dir / "u_seg_012.mov", 48, fps, audio_start=0.0))

    # Seg 13 (51 frames: 20.270 - 22.400 = 2.130s) - CTA B-roll
    s13_raw = seg_dir / "seg_013_raw.mp4"
    assembled.append(assemble_segment(s13_raw, generated_audio["seg13_14"], seg_dir / "u_seg_013.mov", 51, fps, audio_start=0.0))

    # Seg 14 (5 frames: 22.400 - 22.606 = 0.206s) - Outro silence
    s14_raw = seg_dir / "seg_014_raw.mp4"
    assembled.append(assemble_segment(s14_raw, generated_audio["seg13_14"], seg_dir / "u_seg_014.mov", 5, fps, audio_start=51/fps))

    final_output = base_dir / "final_100_percent_uniform_creator_dubbed.mp4"
    join_segments(assembled, final_output, total_frames, fps)

    print("\n=======================================================")
    print(f"SUCCESS! 100% Uniform Master Dubbed Video created at:\n{final_output}")
    print("=======================================================")
    print("Final Video Info:", get_video_info(final_output))

if __name__ == "__main__":
    main()
