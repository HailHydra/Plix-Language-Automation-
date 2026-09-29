import os
import sys
from pathlib import Path
import cv2

sys.path.insert(0, ".")
from src.scene_analyzer import get_video_info, detect_scenes
from src.face_tracker import detect_faces

def main():
    video = Path(r"input\Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL.mp4")
    info = get_video_info(video)
    fps = info["fps"]
    scenes = detect_scenes(video, threshold=32.0)

    print("=== SHOT CLASSIFICATION FOR SUGAR DAMAGE REEL ===")
    cap = cv2.VideoCapture(str(video))
    out_dir = Path("output/sugar_damage_diagnostic_frames")
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, s in enumerate(scenes):
        start_f = int(round(s["start"] * fps))
        end_f = int(round(s["end"] * fps))
        mid_f = (start_f + end_f) // 2

        cap.set(cv2.CAP_PROP_POS_FRAMES, mid_f)
        ret, frame = cap.read()
        if ret:
            cv2.imwrite(str(out_dir / f"scene_{i:02d}_{s['start']:.1f}s.jpg"), frame)
            faces = detect_faces(frame)
            has_face = len(faces) > 0
            face_desc = f"Face detected ({len(faces)})" if has_face else "No face (B-Roll)"
            print(f"Scene #{i:02d}: [{s['start']:5.2f}s - {s['end']:5.2f}s | {s['duration']:4.2f}s] -> {face_desc}")

    cap.release()

if __name__ == "__main__":
    main()
