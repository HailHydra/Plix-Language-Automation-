import cv2

cap = cv2.VideoCapture("output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en/segments/seg_008_raw.mp4")
ret, frame = cap.read()
cap.release()

cv2.imwrite("scripts/seg_008_first_frame.jpg", frame)
print("Saved seg_008_first_frame.jpg")
