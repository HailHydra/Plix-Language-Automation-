import cv2
from pathlib import Path

video_path = Path("output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en/final_dubbed_en.mp4")
cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

frame_idx = 0
prev = None
freezes = []
current_freeze_start = None

while True:
    ret, frame = cap.read()
    if not ret: break
    
    if prev is not None:
        diff = cv2.norm(frame, prev, cv2.NORM_L1) / (frame.shape[0] * frame.shape[1])
        t = frame_idx / fps
        is_frozen = (diff < 0.05)
        
        if is_frozen:
            if current_freeze_start is None:
                current_freeze_start = t
        else:
            if current_freeze_start is not None:
                freeze_dur = t - current_freeze_start
                if freeze_dur >= 0.2:  # frozen for 200ms or more
                    freezes.append((current_freeze_start, t, freeze_dur))
                current_freeze_start = None
    prev = frame
    frame_idx += 1

if current_freeze_start is not None:
    t = frame_idx / fps
    freeze_dur = t - current_freeze_start
    if freeze_dur >= 0.2:
        freezes.append((current_freeze_start, t, freeze_dur))

cap.release()

print(f"Total frames: {frame_idx}, Duration: {frame_idx/fps:.3f}s")
if freezes:
    print(f"Detected {len(freezes)} frozen sections:")
    for start, end, dur in freezes:
        print(f"  FREEZE from {start:.2f}s to {end:.2f}s ({dur:.2f}s, {int(dur*fps)} frames)")
else:
    print("No freezes detected by pixel diff threshold.")
