import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.scene_analyzer import get_video_info

job_dir = Path("output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en")
scenes = json.loads((job_dir / "scenes.json").read_text())
seg_dir = job_dir / "segments"

total_dur = 0
total_frames = 0
for i, scene in enumerate(scenes):
    prefix = f"seg_{i:03d}"
    time_key = f"{int(round(scene['start'] * 1000))}_{int(round(scene['end'] * 1000))}"
    label = scene.get("class")
    
    if label == "A_ROLL":
        if i == 1:
            f = seg_dir / "seg_002_06e4d67d18ea07fc_synced.mp4"
        elif i == 3:
            f = seg_dir / "seg_004_575500960f992f02_synced.mp4"
        elif i == 9:
            f = seg_dir / "seg_009_synced.mp4"
    else:
        files = list(seg_dir.glob(f"{prefix}_{time_key}_*"))
        f = files[0] if files else None

    if f and f.exists():
        info = get_video_info(f)
        total_dur += info["duration"]
        total_frames += info["frame_count"]
        print(f"{prefix} [{scene['start']:.2f}-{scene['end']:.2f}] (exp: {scene['duration']:.2f}s) -> {f.name}: dur={info['duration']:.3f}s, frames={info['frame_count']}, fps={info['fps']}")
    else:
        print(f"{prefix} -> NOT FOUND!")

print(f"Total: {total_dur:.3f}s, {total_frames} frames")
