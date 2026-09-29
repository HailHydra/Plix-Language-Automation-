"""Regenerate the Sugar Damage reel with one voice and one selected face."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2

from src.audio import ffmpeg
from src.common import PipelineError, load_env, write_json
from src.dub_assembly import assemble_segment, join_segments
from src.face_id_tracker import FaceIDTracker
from src.hybrid_clone import generate_tts_voiceover
from src.scene_analyzer import extract_subclip, get_video_info
from src.synclabs_client import SyncLabsClient


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "input/Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL.mp4"
JOB = ROOT / "output/dub_Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL_en"
WORK = JOB / "regenerated_segments"
VOICE_ID = "By6GgyRnUVwstLGTLFod"
BODY_TEXT = (
    "To reduce this damage, start drinking Plix ACV. It flattens insulin spikes, "
    "so your body burns extra sugar for energy. Plus, it controls cravings and "
    "boosts metabolism to melt fat. Just dissolve one tablet in water 30 minutes "
    "before lunch and drink it daily."
)
SCENES = [(0.0, 1.3), (1.3, 2.6), (2.6, 3.8), (3.8, 9.0),
          (9.0, 10.0), (10.0, 11.5), (11.5, 12.5), (12.5, 13.8),
          (13.8, 15.2), (15.2, 17.3), (17.3, 18.3), (18.3, 595 / 30)]


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        raise PipelineError(result.stderr or f"Command failed: {cmd[0]}")
    return result.stdout


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=noprint_wrappers=1:nokey=1", str(path)]).strip())


def master_audio():
    hook = JOB / "hook_clean_fitted.wav"
    if not hook.exists() or abs(duration(hook) - 3.8) > .03:
        raise PipelineError("The existing clean 3.8-second hook is missing or has wrong duration.")
    body_raw = JOB / "regenerated_body_raw.mp3"
    if not body_raw.exists():
        print("Generating the corrected body narration with the existing presenter voice.", flush=True)
        generate_tts_voiceover(VOICE_ID, BODY_TEXT, body_raw)
    body_duration = 595 / 30 - 3.8
    speed = duration(body_raw) / (body_duration - .1)
    if not .8 <= speed <= 1.25:
        raise PipelineError(f"Narration needs {speed:.2f}x speed to fit. Revise the script before continuing.")
    master = JOB / "regenerated_master_audio.wav"
    if not master.exists():
        body = WORK / "body_fitted.wav"
        run([ffmpeg(), "-v", "error", "-nostdin", "-y", "-i", str(body_raw),
             "-af", f"atempo={speed:.8f},apad,atrim=duration={body_duration:.9f}",
             "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(body)])
        run([ffmpeg(), "-v", "error", "-nostdin", "-y", "-i", str(hook), "-i", str(body),
             "-filter_complex", "[0:a]aresample=48000,atrim=duration=3.8,asetpts=PTS-STARTPTS[a];"
             "[1:a]aresample=48000,asetpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=0:a=1[out]",
             "-map", "[out]", "-c:a", "pcm_s16le", str(master)])
    if abs(duration(master) - 595 / 30) > .04:
        raise PipelineError("Regenerated master audio has wrong duration.")
    return master


def main():
    load_env(ROOT / ".env")
    WORK.mkdir(parents=True, exist_ok=True)
    info = get_video_info(SOURCE)
    if info["frame_count"] != 595 or abs(info["fps"] - 30) > .01:
        raise PipelineError("Source footage changed; review scene boundaries before generating.")
    audio = master_audio()
    tracker = FaceIDTracker()
    cap = cv2.VideoCapture(str(SOURCE))
    cap.set(cv2.CAP_PROP_POS_MSEC, 5500)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise PipelineError("Cannot read Dr. Priyanta's reference frame.")
    tracker.set_anchor_from_frame(frame)
    client = SyncLabsClient()
    state_path = JOB / "regenerated_sync_jobs.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    clips = []
    cursor = 0
    for index, (start, end) in enumerate(SCENES):
        first = cursor
        last = round(end * info["fps"]) if index < len(SCENES) - 1 else info["frame_count"]
        cursor = last
        frames = last - first
        exact_start, exact_end = first / info["fps"], last / info["fps"]
        raw = WORK / f"scene_{index:02d}_raw.mp4"
        if not raw.exists():
            extract_subclip(SOURCE, exact_start, exact_end, raw, target_fps=info["fps"])
        video = raw
        paired_audio = audio
        audio_start = exact_start
        # Scene 9 shows the selected woman posing silently; scene 10 is a
        # different woman. Only scene 3 has verified target speech motion.
        if index == 3:
            match = tracker.match_interval(SOURCE, exact_start, exact_end)
            if not match["is_target"] or not match["best"]:
                raise PipelineError(f"Target speaker not verified in scene {index}.")
            audio_clip = WORK / f"scene_{index:02d}_audio.wav"
            if not audio_clip.exists():
                run([ffmpeg(), "-v", "error", "-nostdin", "-y", "-ss", f"{exact_start:.9f}",
                     "-i", str(audio), "-t", f"{frames / info['fps']:.9f}",
                     "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(audio_clip)])
            key = hashlib.sha256(raw.read_bytes() + audio_clip.read_bytes() + b"lipsync-2-pro-v1").hexdigest()[:16]
            saved = WORK / f"scene_{index:02d}_{key}_synced.mp4"
            if not saved.exists():
                record = state.get(str(index), {})
                generation_id = record.get("id") if record.get("key") == key else None
                if not generation_id and index == 3:
                    submission_path = JOB / "regenerated_sync_submission.json"
                    if submission_path.exists():
                        submission = json.loads(submission_path.read_text())
                        generation_id = submission.get("generation_id")
                        if generation_id:
                            state[str(index)] = {"id": generation_id, "key": key,
                                                 "model": "lipsync-2-pro", "face": match["best"]}
                            write_json(state_path, state)
                if not generation_id:
                    video_url = client.upload_file(raw, content_type="video/mp4")
                    audio_url = client.upload_file(audio_clip, content_type="audio/wav")
                    face = match["best"]
                    result = client.generate(video_url, audio_url, model="lipsync-2-pro",
                        options={"sync_mode": "cut_off", "active_speaker_detection": {
                            "auto_detect": False, "frame_number": face["frame_number"],
                            "coordinates": face["coordinates"]}})
                    generation_id = result["id"]
                    state[str(index)] = {"id": generation_id, "key": key, "model": "lipsync-2-pro",
                                         "face": face}
                    write_json(state_path, state)
                print(f"Waiting for scene {index} Sync result {generation_id}...", flush=True)
                result = client.wait_for_completion(generation_id, poll_interval=5, timeout=1200)
                pending = saved.with_suffix(".download.mp4")
                client.download_result(result["outputUrl"], pending)
                pending.replace(saved)
            video, paired_audio, audio_start = saved, saved, 0
        segment = WORK / f"scene_{index:02d}_assembled.mov"
        assemble_segment(video, paired_audio, segment, frames, info["fps"], audio_start)
        clips.append(segment)
        print(f"Assembled scene {index + 1}/{len(SCENES)}", flush=True)
    output = JOB / "final_regenerated_speaker_locked_en.mp4"
    join_segments(clips, output, info["frame_count"], info["fps"])
    print(output, flush=True)


if __name__ == "__main__":
    main()
