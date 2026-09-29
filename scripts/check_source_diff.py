import cv2

cap_final = cv2.VideoCapture("output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en/final_dubbed_en.mp4")
cap_src = cv2.VideoCapture("input/Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL.mp4")

# Check frames around 13.5s to 14.5s
fps = 30.0
for f in range(int(13.4 * fps), int(14.2 * fps)):
    cap_final.set(cv2.CAP_PROP_POS_FRAMES, f)
    ret, frame_f = cap_final.read()
    
    cap_src.set(cv2.CAP_PROP_POS_FRAMES, f)
    ret, frame_s = cap_src.read()
    
    diff = cv2.norm(frame_f, frame_s, cv2.NORM_L1) / (frame_f.shape[0] * frame_f.shape[1])
    print(f"frame {f} (t={f/fps:.3f}s): diff vs source = {diff:.4f}")
