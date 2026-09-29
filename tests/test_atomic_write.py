import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from src.common import write_json, read_json


class AtomicWriteTests(unittest.TestCase):
    def test_transient_windows_lock_retries_without_losing_data(self):
        original = Path.replace
        calls = []
        def replace(path, destination):
            calls.append(str(path))
            if len(calls) == 1:
                raise PermissionError("temporary Windows file lock")
            return original(path, destination)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            with patch.object(Path, "replace", replace), patch("src.common.time.sleep") as sleep:
                write_json(path, {"status": "prepared"})
            self.assertEqual(read_json(path), {"status": "prepared"})
            sleep.assert_called_once()
            self.assertEqual(len(calls), 2)
