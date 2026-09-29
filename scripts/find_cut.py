import cv2

cap = cv2.VideoCapture("input/Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL.mp4")
fps = 30.0

prev = None
for f in range(int(13.4 * fps), int(14.2 * fps)):
    cap.set(cv2.CAP_PROP_POS_FRAMES, f)
    ret, frame = cap.read()
    if prev is not None:
        diff = cv2.norm(frame, prev, cv2.NORM_L1) / (frame.shape[0] * frame.shape[1])
        print(f"source cut test frame {f} (t={f/fps:.3f}s): diff vs prev frame = {diff:.2f}")
    prev = frame
