import os
import sys
from pathlib import Path

sys.path.insert(0, ".")
from src.scene_analyzer import get_video_info, detect_scenes

def main():
    video = Path(r"input\Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL.mp4")
    if not video.exists():
        print(f"Error: {video} does not exist!")
        return
    info = get_video_info(video)
    print("=== NEW INPUT VIDEO INFO ===")
    print(f"File: {video.name}")
    print(f"Resolution: {info['width']}x{info['height']} @ {info['fps']:.3f} fps")
    print(f"Total Frames: {info['frame_count']} ({info['duration']:.3f}s)")

    scenes = detect_scenes(video, threshold=32.0)
    print(f"\nDetected {len(scenes)} scenes:")
    for i, s in enumerate(scenes):
        print(f"Scene #{i:02d}: {s['start']:6.3f}s -> {s['end']:6.3f}s (dur: {s['duration']:5.3f}s)")

if __name__ == "__main__":
    main()
