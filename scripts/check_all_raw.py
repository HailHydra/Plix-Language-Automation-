import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.scene_analyzer import get_video_info
import json

job_dir = Path("output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en")
scenes = json.loads((job_dir / "scenes.json").read_text())
seg_dir = job_dir / "segments"

for i, scene in enumerate(scenes):
    raw = seg_dir / f"seg_{i:03d}_raw.mp4"
    if raw.exists():
        info = get_video_info(raw)
        expected_dur = scene["end"] - scene["start"]
        print(f"seg_{i:03d}: actual={info['duration']:.3f}s (frames={info['frame_count']}), expected={expected_dur:.3f}s, size={raw.stat().st_size}")
    else:
        print(f"seg_{i:03d}: MISSING")
