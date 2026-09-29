import os
import requests
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.common import load_env

def main():
    load_env(".env")
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        print("ELEVENLABS_API_KEY not found in .env")
        return

    headers = {"xi-api-key": key}
    base_dir = Path(r"output\dub_WhatsApp Video 2026-09-28 at 6.01.20 PM_en")
    sample_path = base_dir / "creator_synclab_sample.wav"
    voice_name = "Creator_WhatsApp_Ref"

    # 1. Check if voice already exists on ElevenLabs
    r = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers)
    if not r.ok:
        print(f"Error fetching voices: {r.status_code} {r.text}")
        return

    voices = r.json().get("voices", [])
    matched = next((v for v in voices if v["name"] == voice_name), None)

    if matched:
        voice_id = matched["voice_id"]
        print(f"Found existing cloned voice '{voice_name}' with ID: {voice_id}")
    else:
        print(f"Creating new cloned voice '{voice_name}' from reference audio...")
        with open(sample_path, "rb") as f:
            files = {"files": ("creator_sample.wav", f, "audio/wav")}
            data = {"name": voice_name, "description": "Cloned voice from Sync Labs reference audio"}
            resp = requests.post("https://api.elevenlabs.io/v1/voices/add", headers=headers, data=data, files=files)
            if not resp.ok:
                print(f"Error creating voice: {resp.status_code} {resp.text}")
                return
            voice_id = resp.json()["voice_id"]
            print(f"Created cloned voice ID: {voice_id}")

    # 2. Generate TTS speech with this voice for the initial hook
    hook_text = "Fairies aren't gonna come and make your skin glow while you sleep. Your skin doesn't just get better overnight."
    print(f"Generating TTS for hook: '{hook_text}'")
    
    tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload = {
        "text": hook_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.85,
            "style": 0.0,
            "use_speaker_boost": True
        }
    }

    tts_resp = requests.post(tts_url, headers=headers, json=payload)
    if not tts_resp.ok:
        print(f"Error generating TTS: {tts_resp.status_code} {tts_resp.text}")
        return

    raw_tts_path = base_dir / "broll_cloned_voiceover_raw.mp3"
    with open(raw_tts_path, "wb") as f:
        f.write(tts_resp.content)
    print(f"Saved raw TTS to: {raw_tts_path}")

    # 3. Probe duration of the raw generated speech
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(raw_tts_path)],
        capture_output=True, text=True
    )
    raw_duration = float(probe.stdout.strip())
    print(f"Raw TTS duration: {raw_duration:.3f}s (Target window: 0.160s - 5.589s = 5.429s max speech)")

    # 4. Target B-roll speech timing:
    # Initial silence: 0.16s
    # Max speech duration: 5.589 - 0.160 = 5.429s
    # We want speech to naturally end slightly before 5.589s (e.g. at ~5.30s - 5.45s) for a clean breath before the on-camera shot.
    target_speech_dur = 5.25  # seconds
    tempo_factor = raw_duration / target_speech_dur
    print(f"Applying tempo adjustment (factor: {tempo_factor:.3f}) and padding 0.16s at start...")

    fitted_audio_path = base_dir / "broll_fitted_voiceover.wav"
    # Filter complex:
    # 1. atempo to scale speed to target_speech_dur
    # 2. adelay to insert 160ms pause at the start
    # 3. apad to pad silence up to exactly 5.589s
    delay_ms = 160
    total_segment_duration = 5.589

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", str(raw_tts_path),
        "-af", f"atempo={tempo_factor},adelay={delay_ms}|{delay_ms},apad=whole_dur={total_segment_duration}",
        "-t", f"{total_segment_duration}",
        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(fitted_audio_path)
    ]
    subprocess.run(ffmpeg_cmd, check=True)
    print(f"Fitted audio created: {fitted_audio_path}")

if __name__ == "__main__":
    main()
