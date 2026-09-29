import cv2
from pathlib import Path

v_out = cv2.VideoCapture("output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en/final_dubbed_en.mp4")
v_src = cv2.VideoCapture("input/Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL.mp4")

fps_out = v_out.get(cv2.CAP_PROP_FPS) or 30.0
fps_src = v_src.get(cv2.CAP_PROP_FPS) or 30.0

start_sec = 12.5
end_sec = 15.5

start_frame = int(start_sec * fps_out)
end_frame = int(end_sec * fps_out)

out_dir = Path("scripts/glitch_frames")
out_dir.mkdir(parents=True, exist_ok=True)

# Also check scene 7 and scene 8 files in segments
v_out.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
for i in range(start_frame, end_frame):
    ret, frame = v_out.read()
    if not ret: break
    t = i / fps_out
    # save every 3rd frame or when a sudden change occurs
    if i % 3 == 0 or (13.0 <= t <= 14.5 and i % 2 == 0):
        cv2.imwrite(str(out_dir / f"frame_{i:04d}_t{t:.2f}.jpg"), frame)

print(f"Extracted frames from {start_sec}s to {end_sec}s into {out_dir}")
