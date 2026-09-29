import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, ".")
from src.common import load_env
from src.synclabs_client import SyncLabsClient
from src.scene_analyzer import get_video_info

load_env(".env")

def main():
    video_path = Path(r"input\WhatsApp Video 2026-09-28 at 6.01.20 PM.mp4")
    raw_audio = Path(r"output\dub_WhatsApp Video 2026-09-28 at 6.01.20 PM_en\master_dubbed_audio_en.mp3")
    out_dir = Path(r"output\dub_WhatsApp Video 2026-09-28 at 6.01.20 PM_en")

    info = get_video_info(video_path)
    total_duration = info["duration"]
    print(f"Source video: {video_path.name} | Duration: {total_duration:.3f}s | FPS: {info['fps']:.3f} | Frames: {info['frame_count']}")

    # Match audio duration exactly to video duration
    matched_audio = out_dir / "full_video_matched_dubbed_audio.wav"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_audio),
        "-t", f"{total_duration:.4f}",
        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(matched_audio)
    ], check=True, capture_output=True)
    print(f"Matched audio created: {matched_audio.name}")

    client = SyncLabsClient(default_model="lipsync-2-pro")
    print(f"\n[Sync Labs] Uploading entire video ({video_path.name})...")
    video_url = client.upload_file(video_path, content_type="video/mp4")
    print(f"[Sync Labs] Video URL: {video_url}")

    print(f"\n[Sync Labs] Uploading entire audio ({matched_audio.name})...")
    audio_url = client.upload_file(matched_audio, content_type="audio/wav")
    print(f"[Sync Labs] Audio URL: {audio_url}")

    print(f"\n[Sync Labs] Submitting full 22.6s video to lipsync-2-pro...")
    gen_data = client.generate(video_url, audio_url, model="lipsync-2-pro")
    gen_id = gen_data["id"]
    print(f"[Sync Labs] Generation Job ID: {gen_id}")

    print("\n[Sync Labs] Waiting for generation completion...")
    res = client.wait_for_completion(gen_id, poll_interval=10, timeout=1200)

    out_video_path = out_dir / "final_entire_video_synclabs_pro.mp4"
    print(f"\n[Sync Labs] Downloading finished video to: {out_video_path}...")
    client.download_result(res["outputUrl"], out_video_path)

    print("\n=======================================================")
    print("SUCCESS! Entire video synced continuously via Sync Labs lipsync-2-pro!")
    print(f"Output File: {out_video_path}")
    print("=======================================================")

    res_info = get_video_info(out_video_path)
    print("Synced Video Info:", res_info)

if __name__ == "__main__":
    main()
