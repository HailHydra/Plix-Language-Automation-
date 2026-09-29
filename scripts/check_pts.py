import cv2, subprocess, json
from pathlib import Path

# Run ffprobe to get packet/frame PTS from final_dubbed_en.mp4
cmd = [
    "ffprobe", "-v", "error",
    "-select_streams", "v:0",
    "-show_entries", "frame=pts_time,pkt_dts_time,key_frame",
    "-read_intervals", "3.0%10.0",
    "-of", "json",
    "output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en/final_dubbed_en.mp4"
]
res = subprocess.run(cmd, capture_output=True, text=True)
data = json.loads(res.stdout)
frames = data.get("frames", [])
print(f"Total probed frames in [3s-10s]: {len(frames)}")
for f in frames[:20]:
    print(f["pts_time"], "key=" + str(f.get("key_frame")))
