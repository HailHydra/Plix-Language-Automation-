import base64
import io
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import wave

from src.common import PipelineError, read_json, request_json
from src.srt_parser import parse_srt
from src.audio import RATE, frames, fit
from src.pipeline import prepare, render, edit_segment
from src.elevenlabs_client import ElevenLabs
from src.translation import LibreTranslator


def tone(duration):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        samples = (int(4000 * math.sin(2 * math.pi * 220 * n / RATE))
                   for n in range(round(duration * RATE)))
        audio.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return output.getvalue()


class FakeSpeech:
    def __init__(self, durations):
        self.durations = durations
        self.cache = set()
        self.calls = 0

    def preflight(self):
        pass

    def generate(self, text, cache, revision=0):
        key = (text, revision)
        hit = key in self.cache
        self.cache.add(key)
        self.calls += int(not hit)
        return tone(self.durations.get(text, 0.3)), None, hit


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "input").mkdir()
        self.source = self.root / "input" / "source.srt"
        self.source.write_text(
            "1\n00:00:00,500 --> 00:00:01,500\nHello\n\n"
            "2\n00:00:02,000 --> 00:00:03,000\nWorld\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def job(self):
        return prepare(self.source, self.root / "output", "en", "en")

    def test_parser_unicode_markup_and_bom(self):
        cues = parse_srt("\ufeff1\r\n00:00:00,000 --> 00:00:01,000\r\n<i>പ്രഭാതഭക്ഷണം</i>\r\n")
        self.assertEqual(cues[0].text, "പ്രഭാതഭക്ഷണം")

    def test_parser_rejects_overlap_and_bad_windows(self):
        for text in [
            "1\n00:00:00,000 --> 00:00:01,000\n<i></i>\n<b></b>",
            "1\n00:00:01,000 --> 00:00:00,000\nx",
            "1\n00:00:60,000 --> 00:01:01,000\nx",
            "1\n00:00:00,000 --> 00:00:01,000\nx\n\n2\n00:00:00,500 --> 00:00:02,000\ny",
            "1\n00:00:00,000 --> 00:00:01,000\nx\n\n1\n00:00:02,000 --> 00:00:03,000\ny",
        ]:
            with self.subTest(text=text), self.assertRaises(PipelineError):
                parse_srt(text)

    def test_input_output_separation(self):
        with self.assertRaises(PipelineError):
            prepare(self.source, self.root / "input" / "output", "en", "en")

    def test_translation_file_two_languages(self):
        for target, text in [("ml", "പ്രഭാതഭക്ഷണം"), ("hi", "नाश्ता")]:
            translations = self.root / f"{target}.json"
            translations.write_text(json.dumps({"1": text, "2": text}, ensure_ascii=False), encoding="utf-8")
            job = prepare(self.source, self.root / "output", "en", target, translations=translations)
            self.assertEqual(read_json(job / "manifest.json")["segments"][0]["target_text"], text)

    def test_translation_file_must_cover_all_cues(self):
        translations = self.root / "bad.json"
        translations.write_text('{"1":"Hola"}', encoding="utf-8")
        with self.assertRaises(PipelineError):
            prepare(self.source, self.root / "output", "en", "es", translations=translations)

    def test_timeline_gaps_export_and_cache(self):
        job = self.job()
        speech = FakeSpeech({"Hello": 0.4, "World": 0.5})
        result = render(job, "fake", "fake", mp3=True, client=speech)
        self.assertEqual(result["status"], "ready_for_listening_review")
        self.assertEqual(frames(result["exports"]["wav"]), 3 * RATE)
        self.assertLessEqual(result["mp3_duration_difference_ms"], 25)
        with wave.open(result["exports"]["wav"], "rb") as audio:
            self.assertEqual(audio.readframes(RATE // 2), b"\0\0" * (RATE // 2))
            self.assertNotEqual(audio.readframes(RATE // 10), b"\0\0" * (RATE // 10))
            audio.setpos(RATE)
            self.assertEqual(audio.readframes(RATE), b"\0\0" * RATE)
        render(job, "fake", "fake", client=speech)
        self.assertEqual(speech.calls, 2)
        edit_segment(job, 1, regenerate=True)
        render(job, "fake", "fake", client=speech)
        self.assertEqual(speech.calls, 3)

    def test_overflow_blocks_export_and_clears_stale_references(self):
        job = self.job()
        speech = FakeSpeech({"Hello": 0.4, "World": 0.5, "Long": 1.6})
        render(job, "fake", "fake", client=speech)
        edit_segment(job, 1, text="Long")
        self.assertFalse(read_json(job / "manifest.json")["exports"])
        result = render(job, "fake", "fake", client=speech)
        self.assertEqual(result["status"], "needs_review")
        self.assertFalse(result["exports"])
        self.assertGreater(result["segments"][0]["overflow_ms"], 500)

    def test_small_overflow_is_measured_after_adjustment(self):
        source, destination = self.root / "source.wav", self.root / "fit.wav"
        source.write_bytes(tone(1.04))
        result = fit(source, destination, 1000, 1.1)
        self.assertEqual(result["status"], "adjusted")
        self.assertLessEqual(frames(destination), RATE)
        self.assertLessEqual(result["speed"], 1.1)

    def test_skipped_cue_leaves_silence_and_no_caption(self):
        job = self.job()
        edit_segment(job, 1, skip=True)
        result = render(job, "fake", "fake", client=FakeSpeech({}))
        with wave.open(result["exports"]["wav"], "rb") as audio:
            self.assertEqual(audio.readframes(RATE * 2), b"\0\0" * RATE * 2)
        self.assertNotIn("Hello", Path(result["exports"]["srt"]).read_text())

    def test_lock_and_modified_timing_are_rejected(self):
        job = self.job()
        lock = job / ".lock"
        lock.write_text("123")
        with self.assertRaises(PipelineError):
            edit_segment(job, 1, text="Other")
        lock.unlink()
        data = read_json(job / "manifest.json")
        data["segments"][0]["end_ms"] = 4000
        (job / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(PipelineError):
            render(job, "fake", "fake", client=FakeSpeech({}))


class ProviderTests(unittest.TestCase):
    @patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-only"})
    @patch("src.elevenlabs_client.request_json")
    def test_elevenlabs_contract_and_cache(self, request):
        request.side_effect = [
            [{"model_id": "model", "can_do_text_to_speech": True,
              "languages": [{"language_id": "ml"}], "maximum_text_length_per_request": 5000}],
            {"voice_id": "voice"},
            {"audio_base64": base64.b64encode(b"example audio").decode(), "alignment": None}
        ]
        client = ElevenLabs("model", "voice", "ml")
        client.preflight()
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(client.generate("പ്രഭാതഭക്ഷണം", Path(folder))[2])
            self.assertTrue(client.generate("പ്രഭാതഭക്ഷണം", Path(folder))[2])
        self.assertEqual(request.call_count, 3)
        payload = request.call_args.args[1]
        self.assertEqual(payload["language_code"], "ml")

    @patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-only"})
    @patch("src.elevenlabs_client.request_json")
    def test_unsupported_language_fails_before_generation(self, request):
        request.return_value = [{"model_id": "model", "can_do_text_to_speech": True,
                                 "languages": [{"language_id": "en"}]}]
        with self.assertRaises(PipelineError):
            ElevenLabs("model", "voice", "ml").preflight()
        self.assertEqual(request.call_count, 1)

    @patch.dict(os.environ, {"LIBRETRANSLATE_URL": "http://localhost:5000"})
    @patch("src.translation.request_json")
    def test_translation_contract_and_mixed_detection(self, request):
        translator = LibreTranslator()
        request.side_effect = [
            [{"code": "en", "targets": ["es", "hi"]}],
            {"translatedText": "Hola"},
            [{"language": "en", "confidence": 99}],
            [{"language": "es", "confidence": 99}],
        ]
        translator.validate("en", "es")
        self.assertEqual(translator.translate("Hello", "en", "es"), "Hola")
        cues = parse_srt("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,000 --> 00:00:02,000\nHola")
        with self.assertRaises(PipelineError):
            translator.detect(cues)

    @patch("src.common.time.sleep")
    @patch("src.common.urllib.request.urlopen")
    def test_transient_retry_is_bounded_and_auth_is_not_retried(self, open_url, sleep):
        open_url.side_effect = urllib.error.HTTPError("https://example.test", 429, "limited", {}, None)
        with self.assertRaises(PipelineError):
            request_json("https://example.test", {"text": "x"})
        self.assertEqual(open_url.call_count, 3)
        open_url.reset_mock()
        open_url.side_effect = urllib.error.HTTPError("https://example.test", 401, "auth", {}, None)
        with self.assertRaises(PipelineError):
            request_json("https://example.test")
        self.assertEqual(open_url.call_count, 1)


if __name__ == "__main__":
    unittest.main()
