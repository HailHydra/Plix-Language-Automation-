"""Submit only the selected Sugar Damage presenter shot; resume safely."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import load_env, write_json
from src.synclabs_client import SyncLabsClient

root = Path(__file__).resolve().parents[1]
job = root / "output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en"
work = job / "regenerated_segments"
state_path = job / "regenerated_sync_submission.json"
state = json.loads(state_path.read_text()) if state_path.exists() else {}
load_env(root / ".env")
client = SyncLabsClient()
if "video_url" not in state:
    state["video_url"] = client.upload_file(work / "scene_03_raw.mp4", content_type="video/mp4")
    write_json(state_path, state)
    print("Uploaded presenter video", flush=True)
if "audio_url" not in state:
    state["audio_url"] = client.upload_file(work / "scene_03_audio.wav", content_type="audio/wav")
    write_json(state_path, state)
    print("Uploaded corrected narration excerpt", flush=True)
if "generation_id" not in state:
    result = client.generate(state["video_url"], state["audio_url"], model="lipsync-2-pro",
                             options={"sync_mode": "cut_off", "active_speaker_detection": {
                                 "auto_detect": False, "frame_number": 57, "coordinates": [546, 557]}})
    state["generation_id"] = result["id"]
    write_json(state_path, state)
    print("Submitted presenter shot", flush=True)
