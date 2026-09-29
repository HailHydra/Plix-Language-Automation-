import cv2
from pathlib import Path

seg_dir = Path("output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en/segments")

for f in [
    seg_dir / "seg_002_06e4d67d18ea07fc_synced.mp4",
    seg_dir / "seg_004_575500960f992f02_synced.mp4",
    seg_dir / "seg_009_synced.mp4",
    seg_dir / "seg_003_raw.mp4",
    seg_dir / "seg_009_raw.mp4",
]:
    if not f.exists():
        print(f"{f.name} does not exist")
        continue
    cap = cv2.VideoCapture(str(f))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_idx = 0
    prev = None
    diffs = []
    while True:
        ret, frame = cap.read()
        if not ret: break
        if prev is not None:
            diff = cv2.norm(frame, prev, cv2.NORM_L1) / (frame.shape[0] * frame.shape[1])
            diffs.append(diff)
        prev = frame
        frame_idx += 1
    cap.release()
    avg = sum(diffs)/len(diffs) if diffs else 0
    zeroes = sum(1 for d in diffs if d < 0.05)
    print(f"{f.name}: frames={frame_idx}, avg_diff={avg:.4f}, zero_diff_frames={zeroes}/{len(diffs)}")
