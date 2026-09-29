import subprocess
from pathlib import Path

seg_dir = Path("output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en/segments")
c1 = seg_dir / "seg_002_2600_3800_broll.mp4"
c2 = seg_dir / "seg_004_575500960f992f02_synced.mp4"

manifest = Path("scripts/test_two.txt")
manifest.write_text(f"file '{c1.resolve().as_posix()}'\nfile '{c2.resolve().as_posix()}'\n")

out = Path("scripts/test_two_out.mp4")
cmd = [
    "ffmpeg", "-y", "-nostdin",
    "-f", "concat", "-safe", "0",
    "-i", str(manifest),
    "-vf", "fps=30",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
    str(out)
]
subprocess.run(cmd, capture_output=True, text=True)

import cv2
cap = cv2.VideoCapture(str(out))
cap.set(cv2.CAP_PROP_POS_FRAMES, 50)
ret, f50 = cap.read()
cap.set(cv2.CAP_PROP_POS_FRAMES, 100)
ret, f100 = cap.read()
cap.release()
diff = cv2.norm(f50, f100, cv2.NORM_L1) / (f50.shape[0] * f50.shape[1])
print(f"Diff between frame 50 and frame 100 in two-clip concat: {diff:.4f}")
