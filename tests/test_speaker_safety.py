import unittest
import tempfile
import subprocess
from pathlib import Path
from src.audio import ffmpeg
from src.dub_assembly import route_model
from src.srt_parser import Cue
from src.video_dubbing_pipeline import find_repeated_phrase, audio_only_path


class SpeakerSafetyTests(unittest.TestCase):
    def test_rejected_visible_woman_is_never_lip_synced(self):
        shot = {"is_speech": False, "classification": "b_roll", "face_ratio": 1.0,
                "reason": "Face does not match speaker"}
        self.assertIsNone(route_model(shot, "lipsync-2-pro", "lipsync-2"))

    def test_bad_hook_is_detected_before_generation(self):
        cues = [Cue(1, 320, 4500, "This is sugar damage. This is sugar damage. This is sugar damage.")]
        self.assertEqual(find_repeated_phrase(cues), ("this is sugar damage", .32))
        clean = [Cue(1, 320, 4500, "This is sugar damage. To reduce it, drink Plix ACV.")]
        self.assertIsNone(find_repeated_phrase(clean))

    def test_video_returned_as_mp3_name_is_extracted_to_audio_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "dubbed.mp3"
            subprocess.run([ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i",
                            "color=black:size=64x64:rate=25", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=48000", "-t", "1", "-c:v",
                            "libx264", "-c:a", "aac", "-f", "mp4", str(media)], check=True)
            extracted = audio_only_path(media)
            self.assertNotEqual(extracted, media)
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                    "stream=codec_type", "-of", "csv=p=0", str(extracted)],
                                   capture_output=True, text=True, check=True)
            self.assertEqual(probe.stdout.strip(), "audio")
            self.assertTrue(media.exists())
