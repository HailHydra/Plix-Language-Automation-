import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.scene_analyzer import get_video_info


seg_dir = Path("output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en/segments")
for name in [
    "seg_007_raw.mp4",
    "seg_007_12500_13800_broll.mp4",
    "seg_008_raw.mp4",
    "seg_008_13800_15200_broll.mp4",
    "seg_009_raw.mp4",
    "seg_009_synced.mp4"
]:
    p = seg_dir / name
    if p.exists():
        info = get_video_info(p)
        print(f"{name}: dur={info['duration']:.3f}s, frames={info['frame_count']}, size={p.stat().st_size}")
    else:
        print(f"{name}: NOT FOUND")
