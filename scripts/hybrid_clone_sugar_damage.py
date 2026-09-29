import os
import sys
import json
import time
import requests
import subprocess
from pathlib import Path

sys.path.insert(0, ".")
from src.common import load_env, PipelineError
from src.scene_analyzer import get_video_info, extract_subclip
from src.dub_assembly import assemble_segment, join_segments
from src.hybrid_clone import ensure_voice_clone, generate_tts_voiceover, time_fit_voiceover

load_env(".env")

def main():
    source_video = Path(r"input\Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL.mp4")
    job_dir = Path(r"output\dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en")
    seg_dir = job_dir / "segments"

    info = get_video_info(source_video)
    fps = info["fps"]
    total_frames = info["frame_count"]
    total_duration = info["duration"]

    print(f"\n=======================================================")
    print(f"[Hybrid Clone] Target Video: {source_video.name}")
    print(f"[Hybrid Clone] Info: {info['width']}x{info['height']} @ {fps:.3f}fps, {total_duration:.2f}s ({total_frames} frames)")
    print(f"=======================================================\n")

    # Step 1: Voice Sample Extraction from Talking Head
    # Seg 004 (3.80s - 9.00s) has 5.2 seconds of clear English speech from Sync Labs!
    seg4_synced = seg_dir / "seg_004_575500960f992f02_synced.mp4"
    if not seg4_synced.exists():
        raise RuntimeError(f"Missing seg4_synced: {seg4_synced}")

    sample_wav = job_dir / "creator_sugar_damage_sample.wav"
    if not sample_wav.exists() or sample_wav.stat().st_size == 0:
        print("[Hybrid Clone] Extracting reference vocal sample from Seg 004 talking head...")
        subprocess.run([
            "ffmpeg", "-y", "-i", str(seg4_synced),
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1",
            str(sample_wav)
        ], check=True, capture_output=True)
        print(f"Sample extracted: {sample_wav.name}")

    # Step 2: Instant Voice Clone on ElevenLabs
    voice_name = "Creator_SugarDamage_Ref"
    voice_id = ensure_voice_clone(sample_wav, voice_name=voice_name)

    # Step 3: Generate and time-fit B-roll Opening Hook (0.00s - 3.80s = 3.80s duration)
    # Text: "This is sugar damage. This is sugar damage. This is sugar damage."
    hook_text = "This is sugar damage. This is sugar damage. This is sugar damage."
    broll_raw = job_dir / "hook_cloned_raw.mp3"
    broll_fitted = job_dir / "hook_cloned_fitted.wav"

    print(f"[Hybrid Clone] Generating TTS for opening hook: '{hook_text}'")
    generate_tts_voiceover(voice_id, hook_text, broll_raw)
    time_fit_voiceover(broll_raw, broll_fitted, target_duration=3.800, delay_ms=100)
    print(f"[Hybrid Clone] Time-fitted B-roll hook audio: {broll_fitted.name}")

    # Step 4: Assemble Segments Frame-by-Frame
    # Total frames: 595
    # Seg 0: 0.00s - 0.32s (10 frames) -> Silence / pause
    # Seg 1: 0.32s - 1.30s (29 frames: frames 10 to 39) -> B-roll Hook 1
    # Seg 2: 1.30s - 2.60s (39 frames: frames 39 to 78) -> B-roll Hook 2
    # Seg 3: 2.60s - 3.80s (36 frames: frames 78 to 114) -> B-roll Hook 3
    # Seg 4: 3.80s - 9.00s (156 frames: frames 114 to 270) -> Talking Head (Sync Labs)
    # Seg 5: 9.00s - 10.00s (30 frames: frames 270 to 300) -> Silent posing B-roll
    # Seg 6: 10.00s - 11.50s (45 frames: frames 300 to 345) -> Talking Head (Sync Labs)
    # Seg 7: 11.50s - 12.50s (30 frames: frames 345 to 375) -> Talking Head (Sync Labs)
    # Seg 8: 12.50s - 13.80s (39 frames: frames 375 to 414) -> Product B-roll
    # Seg 9: 13.80s - 15.20s (42 frames: frames 414 to 456) -> Product B-roll
    # Seg 10: 15.20s - 17.30s (63 frames: frames 456 to 519) -> Product B-roll
    # Seg 11: 17.30s - 18.30s (30 frames: frames 519 to 549) -> Talking Head
    # Seg 12: 18.30s - 19.833s (46 frames: frames 549 to 595) -> Outro silence

    master_dubbed_audio = job_dir / "master_dubbed_audio_en.mp3"
    assembled = []

    # Seg 0 (10 frames)
    s0_raw = seg_dir / "seg_000_23e92a49e22905da_raw.mp4"
    assembled.append(assemble_segment(s0_raw, broll_fitted, seg_dir / "h_seg_000.mov", 10, fps, audio_start=0.0))

    # Seg 1 (29 frames: start at 10/fps = 0.333s)
    s1_raw = seg_dir / "seg_001_6ba28aa3fc70e562_raw.mp4"
    assembled.append(assemble_segment(s1_raw, broll_fitted, seg_dir / "h_seg_001.mov", 29, fps, audio_start=10/fps))

    # Seg 2 (39 frames: start at 39/fps = 1.300s)
    s2_raw = seg_dir / "seg_002_06e4d67d18ea07fc_raw.mp4"
    assembled.append(assemble_segment(s2_raw, broll_fitted, seg_dir / "h_seg_002.mov", 39, fps, audio_start=39/fps))

    # Seg 3 (36 frames: start at 78/fps = 2.600s)
    s3_raw = seg_dir / "seg_003_fa4b5999b8be4835_raw.mp4"
    assembled.append(assemble_segment(s3_raw, broll_fitted, seg_dir / "h_seg_003.mov", 36, fps, audio_start=78/fps))

    # Seg 4 (156 frames) - Talking Head
    assembled.append(assemble_segment(seg4_synced, seg4_synced, seg_dir / "h_seg_004.mov", 156, fps, audio_start=0.0))

    # Seg 5 (30 frames: 9.0s - 10.0s) - B-roll posing with master audio
    s5_raw = seg_dir / "seg_005_75ef2839fee95262_raw.mp4"
    assembled.append(assemble_segment(s5_raw, master_dubbed_audio, seg_dir / "h_seg_005.mov", 30, fps, audio_start=9.00))

    # Seg 6 (45 frames: 10.0s - 11.5s) - Talking Head
    seg6_synced = seg_dir / "seg_006_96dc999c46070324_synced.mp4"
    assembled.append(assemble_segment(seg6_synced, seg6_synced, seg_dir / "h_seg_006.mov", 45, fps, audio_start=0.0))

    # Seg 7 (30 frames: 11.5s - 12.5s) - Talking Head
    seg7_synced = seg_dir / "seg_007_7d34382c71a4ad2b_synced.mp4"
    assembled.append(assemble_segment(seg7_synced, seg7_synced, seg_dir / "h_seg_007.mov", 30, fps, audio_start=0.0))

    # Seg 8 (39 frames: 12.5s - 13.8s) - Product B-roll
    s8_raw = seg_dir / "seg_008_raw.mp4"
    if not s8_raw.exists(): extract_subclip(source_video, 12.5, 13.8, s8_raw, target_fps=fps)
    assembled.append(assemble_segment(s8_raw, master_dubbed_audio, seg_dir / "h_seg_008.mov", 39, fps, audio_start=12.50))

    # Seg 9 (42 frames: 13.8s - 15.2s) - Product B-roll
    s9_raw = seg_dir / "seg_009_raw.mp4"
    if not s9_raw.exists(): extract_subclip(source_video, 13.8, 15.2, s9_raw, target_fps=fps)
    assembled.append(assemble_segment(s9_raw, master_dubbed_audio, seg_dir / "h_seg_009.mov", 42, fps, audio_start=13.80))

    # Seg 10 (63 frames: 15.2s - 17.3s) - Product B-roll
    s10_raw = seg_dir / "seg_010_raw.mp4"
    if not s10_raw.exists(): extract_subclip(source_video, 15.2, 17.3, s10_raw, target_fps=fps)
    assembled.append(assemble_segment(s10_raw, master_dubbed_audio, seg_dir / "h_seg_010.mov", 63, fps, audio_start=15.20))

    # Seg 11 (30 frames: 17.3s - 18.3s) - Talking Head / Call-to-action
    s11_raw = seg_dir / "seg_011_raw.mp4"
    if not s11_raw.exists(): extract_subclip(source_video, 17.3, 18.3, s11_raw, target_fps=fps)
    assembled.append(assemble_segment(s11_raw, master_dubbed_audio, seg_dir / "h_seg_011.mov", 30, fps, audio_start=17.30))

    # Seg 12 (46 frames: 18.3s - 19.833s) - Outro
    s12_raw = seg_dir / "seg_012_raw.mp4"
    if not s12_raw.exists(): extract_subclip(source_video, 18.3, 19.833, s12_raw, target_fps=fps)
    assembled.append(assemble_segment(s12_raw, master_dubbed_audio, seg_dir / "h_seg_012.mov", 46, fps, audio_start=18.30))

    print(f"\n[Hybrid Clone] Total segments to join: {len(assembled)}")
    final_output = job_dir / "final_hybrid_cloned_sugar_damage_dubbed_en.mp4"
    join_segments(assembled, final_output, total_frames, fps)

    print("\n=======================================================")
    print(f"SUCCESS! Hybrid Cloned Video created at:\n{final_output}")
    print("=======================================================")

    final_info = get_video_info(final_output)
    print("Final Video Info:", final_info)

if __name__ == "__main__":
    main()
