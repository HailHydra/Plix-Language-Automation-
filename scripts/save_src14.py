import cv2

cap = cv2.VideoCapture("input/Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL.mp4")
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
cap.set(cv2.CAP_PROP_POS_FRAMES, int(14.0 * fps))
ret, frame = cap.read()
cap.release()

cv2.imwrite("scripts/source_at_14s.jpg", frame)
print("Saved source_at_14s.jpg")
