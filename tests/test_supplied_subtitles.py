import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.common import PipelineError, read_json
from src.pipeline import prepare, render
from src.input_formats import split_bilingual
from test_pipeline import FakeSpeech


class SuppliedSubtitleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "input").mkdir()
        self.source = self.root / "input" / "source.srt"
        self.source.write_text("1\n00:00:00,000 --> 00:00:02,000\nBreakfast is ready.\nപ്രഭാതഭക്ഷണം തയ്യാറാണ്.\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    @patch("src.pipeline.LibreTranslator", side_effect=AssertionError("Translation must be bypassed"))
    def test_bilingual_synthesizes_only_target_text(self, translator):
        job = prepare(self.source, self.root / "output", "en", "ml", bilingual=True)
        result = read_json(job / "manifest.json")
        self.assertEqual(result["segments"][0]["source_text"], "Breakfast is ready.")
        self.assertEqual(result["segments"][0]["target_text"], "പ്രഭാതഭക്ഷണം തയ്യാറാണ്.")
        self.assertEqual(result["segments"][0]["available_ms"], 2000)
        speech = FakeSpeech({})
        result = render(job, "fake", "fake", client=speech)
        self.assertEqual(result["status"], "ready_for_listening_review")
        self.assertEqual(speech.cache, {("പ്രഭാതഭക്ഷണം തയ്യാറാണ്.", 0)})
        self.assertNotIn("Breakfast", Path(result["exports"]["srt"]).read_text(encoding="utf-8"))
        self.assertIn("Breakfast", (job / "source.srt").read_text(encoding="utf-8"))
        translator.assert_not_called()

    def test_source_wrap_and_target_wrap(self):
        raw = "1\n00:00:00,000 --> 00:00:02,000\n<i>Breakfast is</i>\nready.\nപ്രഭാതഭക്ഷണം\nതയ്യാറാണ്.\n"
        sources, targets = split_bilingual(raw, source_lines=2)
        self.assertEqual(sources[0].text, "Breakfast is ready.")
        self.assertEqual(targets["1"], "പ്രഭാതഭക്ഷണം തയ്യാറാണ്.")

    def test_same_alphabet_and_reverse_order(self):
        raw = "1\n00:00:00,000 --> 00:00:02,000\nEl desayuno está listo.\nBreakfast is ready.\n"
        sources, targets = split_bilingual(raw, source_first=False)
        self.assertEqual(sources[0].text, "Breakfast is ready.")
        self.assertEqual(targets["1"], "El desayuno está listo.")

    def test_missing_translation_is_rejected(self):
        with self.assertRaises(PipelineError):
            split_bilingual("1\n00:00:00,000 --> 00:00:02,000\nEnglish only")
        for count in [0, -1, 1.5]:
            with self.assertRaises(PipelineError):
                split_bilingual(self.source.read_text(encoding="utf-8"), source_lines=count)

    @patch("src.pipeline.LibreTranslator", side_effect=AssertionError("No translation provider"))
    def test_paired_srt_matches_windows_and_allows_different_ids(self, translator):
        self.source.write_text("1\n00:00:00,000 --> 00:00:02,000\nBreakfast is ready.\n", encoding="utf-8")
        target = self.root / "input" / "target.srt"
        target.write_text("99\n00:00:00,000 --> 00:00:02,000\nEl desayuno está listo.\n", encoding="utf-8")
        job = prepare(self.source, self.root / "output", "en", "es", translated_srt=target)
        result = read_json(job / "manifest.json")
        self.assertEqual(result["segments"][0]["id"], 1)
        self.assertEqual(result["segments"][0]["target_text"], "El desayuno está listo.")
        self.assertTrue((job / "translated_input.srt").exists())
        translator.assert_not_called()

    def test_paired_srt_rejects_wrong_windows_and_counts(self):
        target = self.root / "input" / "target.srt"
        for raw in [
            "1\n00:00:00,000 --> 00:00:01,999\nHola",
            "1\n00:00:00,000 --> 00:00:02,000\nHola\n\n2\n00:00:02,000 --> 00:00:03,000\nMundo",
        ]:
            target.write_text(raw, encoding="utf-8")
            with self.assertRaises(PipelineError):
                prepare(self.source, self.root / "output", "en", "es", translated_srt=target)

    def test_explicit_languages_and_exclusive_input_required(self):
        with self.assertRaises(PipelineError):
            prepare(self.source, self.root / "output", "auto", "ml", bilingual=True)
        with self.assertRaises(PipelineError):
            prepare(self.source, self.root / "output", "en", "ml", bilingual=True, translated_srt=self.source)

    def test_ui_imports_bilingual_upload_without_translation_provider(self):
        from streamlit.testing.v1 import AppTest
        project = Path(__file__).resolve().parents[1]
        script = (project / "app.py").read_text(encoding="utf-8").replace(
            "ROOT = Path(__file__).resolve().parent", f"ROOT = Path({str(self.root)!r})")
        uploaded = io.BytesIO(self.source.read_bytes())
        with patch("streamlit.file_uploader", return_value=uploaded), patch(
            "src.pipeline.LibreTranslator", side_effect=AssertionError("No translation provider")
        ):
            app = AppTest.from_string(script).run(timeout=30)
            self.assertFalse(app.exception)
            next(button for button in app.button if button.label == "Prepare text").click()
            app.run(timeout=30)
        self.assertFalse(app.exception)
        jobs = list((self.root / "output").glob("*/manifest.json"))
        self.assertEqual(len(jobs), 1)
        result = read_json(jobs[0])
        self.assertEqual(result["input_format"], "bilingual_srt")
        self.assertEqual(result["segments"][0]["target_text"], "പ്രഭാതഭക്ഷണം തയ്യാറാണ്.")
