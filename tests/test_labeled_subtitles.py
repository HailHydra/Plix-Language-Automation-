import unittest
from src.common import PipelineError
from src.input_formats import split_labeled_bilingual


class LabeledSubtitleTests(unittest.TestCase):
    def test_explicit_marathi_label_with_wrapping_and_reversed_order(self):
        raw = "1\n00:00:00,500 --> 00:00:03,000\n[Marathi]: ??? ???????\n??????\n[English]: High protein breakfast\n"
        source, target = split_labeled_bilingual(raw, "English", "Marathi")
        self.assertEqual(source[0].text, "High protein breakfast")
        self.assertEqual(target["1"], "??? ??????? ??????")
        self.assertNotIn("Marathi", target["1"])
        self.assertEqual((source[0].start_ms, source[0].end_ms), (500, 3000))

    def test_missing_duplicate_and_unexpected_labels_rejected(self):
        for text in [
            "[English]: Hello",
            "[English]: Hello\n[Marathi]: ???????\n[Marathi]: ??????",
            "[English]: Hello\n[Hindi]: ??????",
            "Unlabeled English\n[Marathi]: ???????",
            "[English]: Hello\n[Marathi]:",
        ]:
            with self.subTest(text=text), self.assertRaises(PipelineError):
                split_labeled_bilingual("1\n00:00:00,000 --> 00:00:01,000\n" + text, "English", "Marathi")

    def test_labels_are_case_insensitive_and_require_distinct_values(self):
        raw = "1\n00:00:00,000 --> 00:00:01,000\n[ENGLISH]: Hello\n[marathi]: ???????"
        self.assertEqual(split_labeled_bilingual(raw, "English", "Marathi")[1]["1"], "???????")
        for source, target in [("", "Marathi"), ("English", "english")]:
            with self.assertRaises(PipelineError):
                split_labeled_bilingual(raw, source, target)
