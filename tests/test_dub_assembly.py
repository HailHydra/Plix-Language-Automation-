import tempfile
import subprocess
import unittest
from pathlib import Path
from src.audio import ffmpeg
from src.common import PipelineError
from src.dub_assembly import route_model, assemble_segment, join_segments
from src.scene_analyzer import get_video_info


class AssemblyTests(unittest.TestCase):
    def test_routes(self):
        self.assertEqual(route_model({'is_speech': True}, 'lipsync-2-pro', 'lipsync-2'), 'lipsync-2-pro')
        self.assertIsNone(route_model({'classification': 'b_roll', 'face_ratio': .9}, 'lipsync-2-pro', 'lipsync-2'))
        self.assertIsNone(route_model({'classification': 'b_roll', 'face_ratio': 0}, 'lipsync-2-pro', 'lipsync-2'))
        self.assertIsNone(route_model({'is_speech': False}, 'lipsync-2-pro', 'lipsync-2'))

    def test_repeated_segments_have_exact_frame_count_and_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.mp4'
            subprocess.run([ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'testsrc2=size=160x120:rate=24000/1001', '-f', 'lavfi', '-i',
                            'sine=frequency=440:sample_rate=48000', '-t', '1',
                            '-c:v', 'libx264', '-c:a', 'aac', str(source)], check=True)
            fps = 24000 / 1001
            clips = []
            for i, n in enumerate([5, 7, 11]):
                clips.append(assemble_segment(source, source, root / f'{i}.mov', n, fps))
            output = root / 'result.mp4'
            join_segments(clips, output, 23, fps)
            self.assertEqual(get_video_info(output)['frame_count'], 23)
            decoded = subprocess.run([ffmpeg(), '-v', 'error', '-i', str(output), '-vn',
                                      '-f', 's16le', '-ac', '1', 'pipe:1'], capture_output=True, check=True)
            self.assertGreater(len(decoded.stdout), 80000)
            with self.assertRaises(PipelineError):
                assemble_segment(source, source, root / 'short.mov', 100, fps)

    def test_preview_seek_moves_video_with_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.mp4'
            subprocess.run([ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'testsrc2=size=160x120:rate=25', '-f', 'lavfi', '-i',
                            'sine=frequency=440:sample_rate=48000', '-t', '2',
                            '-c:v', 'libx264', '-c:a', 'aac', str(source)], check=True)
            result = assemble_segment(source, source, root / 'preview.mov', 25, 25,
                                      audio_start=1, video_start=1)
            self.assertEqual(get_video_info(result)['frame_count'], 25)
            with self.assertRaises(PipelineError):
                assemble_segment(source, source, root / 'overflow.mov', 30, 25,
                                 audio_start=1, video_start=1)
