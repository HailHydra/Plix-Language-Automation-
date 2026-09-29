import cv2
from pathlib import Path

video_path = Path("output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en/final_dubbed_en.mp4")
cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

# Read frame at 4.0s and frame at 8.0s
cap.set(cv2.CAP_PROP_POS_FRAMES, int(4.0 * fps))
ret, frame_4 = cap.read()

cap.set(cv2.CAP_PROP_POS_FRAMES, int(8.0 * fps))
ret, frame_8 = cap.read()

cap.release()

diff = cv2.norm(frame_4, frame_8, cv2.NORM_L1) / (frame_4.shape[0] * frame_4.shape[1])
print(f"Diff between t=4.0s and t=8.0s: {diff:.4f}")
