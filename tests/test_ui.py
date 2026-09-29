import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from src.common import read_json
from src.pipeline import prepare
from test_pipeline import FakeSpeech

ROOT = Path(__file__).resolve().parents[1]


class ReviewUITests(unittest.TestCase):
    def test_edit_generate_and_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "input").mkdir()
            source = root / "input" / "sample.srt"
            source.write_text("1\n00:00:00,500 --> 00:00:02,000\nHello\n", encoding="utf-8")
            job = prepare(source, root / "output", "en", "en")
            script = (ROOT / "app.py").read_text(encoding="utf-8").replace(
                "ROOT = Path(__file__).resolve().parent", f"ROOT = Path({str(root)!r})")
            app = AppTest.from_string(script).run(timeout=30)
            self.assertFalse(app.exception)
            app.text_area[0].set_value("Edited")
            next(b for b in app.button if b.label == "Save cue").click()
            app.run(timeout=30)
            self.assertFalse(app.exception)
            self.assertEqual(read_json(job / "manifest.json")["segments"][0]["target_text"], "Edited")
            next(t for t in app.text_input if t.label == "ElevenLabs voice ID").set_value("fake")
            next(c for c in app.checkbox if c.label == "I reviewed the text and want to generate speech").check()
            app.run(timeout=30)
            next(b for b in app.button if b.label == "Generate / resume").click()
            with patch("src.pipeline.ElevenLabs", return_value=FakeSpeech({})):
                app.run(timeout=30)
            self.assertFalse(app.exception)
            result = read_json(job / "manifest.json")
            self.assertEqual(result["status"], "ready_for_listening_review")
            self.assertTrue(Path(result["exports"]["wav"]).exists())
            self.assertTrue(app.get("download_button"))
