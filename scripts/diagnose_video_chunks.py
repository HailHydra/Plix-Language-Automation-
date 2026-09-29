import os
import sys
from pathlib import Path
import cv2

sys.path.insert(0, ".")
from src.scene_analyzer import detect_scenes, get_video_info
from src.face_tracker import detect_faces

def main():
    video_path = Path(r"input\WhatsApp Video 2026-09-28 at 6.01.20 PM.mp4")
    info = get_video_info(video_path)
    print("=== VIDEO INFO ===")
    print(f"File: {video_path.name}")
    print(f"Dimensions: {info['width']}x{info['height']} @ {info['fps']:.3f} fps")
    print(f"Total Frames: {info['frame_count']} ({info['duration']:.3f}s)")

    scenes = detect_scenes(video_path, threshold=32.0)
    print(f"\n=== SCENE CUTS DETECTED ({len(scenes)}) ===")
    for i, s in enumerate(scenes):
        print(f"Scene #{i:02d}: {s['start']:6.3f}s -> {s['end']:6.3f}s (dur: {s['duration']:5.3f}s)")

    print("\n=== FRAME-BY-FRAME SHOT VISUAL ANALYSIS ===")
    cap = cv2.VideoCapture(str(video_path))
    for i, s in enumerate(scenes):
        start_frame = int(round(s['start'] * info['fps']))
        end_frame = int(round(s['end'] * info['fps']))
        dur_frames = end_frame - start_frame

        faces_found = 0
        tested_frames = 0
        step = max(1, dur_frames // 5)

        for f_idx in range(start_frame, end_frame, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if not ret:
                break
            tested_frames += 1
            faces = detect_faces(frame)
            if len(faces) > 0:
                faces_found += 1

        face_pct = (faces_found / tested_frames * 100) if tested_frames > 0 else 0
        print(f"Scene #{i:02d} [{s['start']:5.2f}s - {s['end']:5.2f}s | {dur_frames:3d} frames]: Face presence = {faces_found}/{tested_frames} ({face_pct:5.1f}%)")

    cap.release()

if __name__ == "__main__":
    main()
