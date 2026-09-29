import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
from src.common import PipelineError
from src.dubbing_client import ElevenLabsDubbingClient
from src.face_tracker import auto_detect_creator_anchor, classify_shot_voiceover_aware
from src.srt_parser import Cue
from src.synclabs_client import SyncLabsClient
from src.video_dubbing_pipeline import (
    extract_audio_segment,
    extract_source_audio,
    run_video_dubbing_pipeline,
    select_speech_intervals,
)


class TestElevenLabsDubbingClient(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.sample_media = self.temp_dir / "sample.mp4"
        self.sample_media.write_bytes(b"dummy mp4 content")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PipelineError):
                ElevenLabsDubbingClient()

    @patch("requests.post")
    def test_create_dub_job_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"dubbing_id": "dub_12345", "expected_duration_sec": 30.0}
        mock_post.return_value = mock_resp

        client = ElevenLabsDubbingClient(api_key="test_key")
        job_id = client.create_dub_job(self.sample_media, target_lang="es", source_lang="en")

        self.assertEqual(job_id, "dub_12345")
        self.assertTrue(mock_post.called)
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["data"]["target_lang"], "es")
        self.assertEqual(call_kwargs["headers"]["xi-api-key"], "test_key")

    @patch("requests.post")
    def test_create_dub_job_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"detail": "Invalid language code"}
        mock_post.return_value = mock_resp

        client = ElevenLabsDubbingClient(api_key="test_key")
        with self.assertRaises(PipelineError):
            client.create_dub_job(self.sample_media, target_lang="invalid")

    @patch("requests.get")
    def test_wait_for_completion_success(self, mock_get):
        resp_dubbing = MagicMock(status_code=200)
        resp_dubbing.json.return_value = {"status": "dubbing"}
        resp_dubbed = MagicMock(status_code=200)
        resp_dubbed.json.return_value = {"status": "dubbed"}
        mock_get.side_effect = [resp_dubbing, resp_dubbed]

        client = ElevenLabsDubbingClient(api_key="test_key")
        result = client.wait_for_completion("dub_12345", poll_interval=0.01)
        self.assertEqual(result["status"], "dubbed")

    @patch("requests.get")
    def test_wait_for_completion_failed_job(self, mock_get):
        resp_failed = MagicMock(status_code=200)
        resp_failed.json.return_value = {"status": "failed", "error": "Transcription error"}
        mock_get.return_value = resp_failed

        client = ElevenLabsDubbingClient(api_key="test_key")
        with self.assertRaises(PipelineError) as ctx:
            client.wait_for_completion("dub_12345", poll_interval=0.01)
        self.assertIn("ElevenLabs Dubbing job failed", str(ctx.exception))

    @patch("requests.get")
    def test_download_dubbed_audio(self, mock_get):
        mock_resp = MagicMock(status_code=200)
        mock_resp.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_resp.__enter__.return_value = mock_resp
        mock_get.return_value = mock_resp

        out_audio = self.temp_dir / "dubbed.mp3"
        client = ElevenLabsDubbingClient(api_key="test_key")
        res_path = client.download_dubbed_audio("dub_12345", "es", out_audio)

        self.assertTrue(res_path.exists())
        self.assertEqual(res_path.read_bytes(), b"chunk1chunk2")

    @patch("requests.get")
    def test_download_transcript(self, mock_get):
        srt_content = "1\n00:00:01,000 --> 00:00:03,000\nHola mundo\n"
        mock_resp = MagicMock(status_code=200, text=srt_content)
        mock_get.return_value = mock_resp

        out_srt = self.temp_dir / "transcript.srt"
        client = ElevenLabsDubbingClient(api_key="test_key")
        cues = client.download_transcript("dub_12345", "es", out_srt, format_type="srt")

        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].text, "Hola mundo")
        self.assertEqual(cues[0].start_ms, 1000)
        self.assertEqual(cues[0].end_ms, 3000)


class TestSyncLabsClient(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.sample_file = self.temp_dir / "video.mp4"
        self.sample_file.write_bytes(b"dummy video data")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PipelineError):
                SyncLabsClient()

    @patch("requests.post")
    @patch("requests.put")
    def test_upload_file_3_step_flow(self, mock_put, mock_post):
        # Step 1 response
        r1 = MagicMock(status_code=200)
        r1.json.return_value = {
            "uploadUrl": "https://storage.sync.so/presigned-put",
            "url": "https://storage.sync.so/canonical/video.mp4"
        }
        # Step 3 response
        r3 = MagicMock(status_code=200)
        r3.json.return_value = {"id": "asset_123", "url": "https://storage.sync.so/canonical/video.mp4"}

        mock_post.side_effect = [r1, r3]
        mock_put.return_value = MagicMock(status_code=200)

        client = SyncLabsClient(api_key="sync_key")
        canonical_url = client.upload_file(self.sample_file, content_type="video/mp4")

        self.assertEqual(canonical_url, "https://storage.sync.so/canonical/video.mp4")
        self.assertTrue(mock_put.called)
        put_kwargs = mock_put.call_args[1]
        self.assertEqual(put_kwargs["headers"]["Content-Type"], "video/mp4")
        self.assertEqual(mock_post.call_args_list[1][1]["json"]["type"], "VIDEO")

    @patch("requests.post")
    def test_generate_default_lipsync_2_pro(self, mock_post):
        mock_resp = MagicMock(status_code=201)
        mock_resp.json.return_value = {"id": "gen_987", "status": "PENDING"}
        mock_post.return_value = mock_resp

        client = SyncLabsClient(api_key="sync_key")
        res = client.generate(
            video_url="https://video.mp4",
            audio_url="https://audio.wav"
        )
        self.assertEqual(res["id"], "gen_987")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["model"], "lipsync-2-pro")
        self.assertEqual(payload["input"][0]["url"], "https://video.mp4")

    @patch("requests.post")
    def test_generate_explicit_model_override(self, mock_post):
        mock_resp = MagicMock(status_code=201)
        mock_resp.json.return_value = {"id": "gen_987", "status": "PENDING"}
        mock_post.return_value = mock_resp

        client = SyncLabsClient(api_key="sync_key")
        res = client.generate(
            video_url="https://video.mp4",
            audio_url="https://audio.wav",
            model="lipsync-2"
        )
        self.assertEqual(res["id"], "gen_987")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["model"], "lipsync-2")

    @patch("requests.get")
    def test_wait_for_completion_success(self, mock_get):
        r_processing = MagicMock(status_code=200)
        r_processing.json.return_value = {"id": "gen_987", "status": "PROCESSING"}
        r_completed = MagicMock(status_code=200)
        r_completed.json.return_value = {
            "id": "gen_987",
            "status": "COMPLETED",
            "outputUrl": "https://storage.sync.so/output.mp4"
        }
        mock_get.side_effect = [r_processing, r_completed]

        client = SyncLabsClient(api_key="sync_key")
        res = client.wait_for_completion("gen_987", poll_interval=0.01)
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(res["outputUrl"], "https://storage.sync.so/output.mp4")

    @patch("requests.get")
    def test_wait_for_completion_failure(self, mock_get):
        r_failed = MagicMock(status_code=200)
        r_failed.json.return_value = {
            "id": "gen_987",
            "status": "FAILED",
            "error": "Face detection failed in visual input"
        }
        mock_get.return_value = r_failed

        client = SyncLabsClient(api_key="sync_key")
        with self.assertRaises(PipelineError) as ctx:
            client.wait_for_completion("gen_987", poll_interval=0.01)
        self.assertIn("Face detection failed", str(ctx.exception))

    @patch("requests.get")
    def test_download_result(self, mock_get):
        mock_resp = MagicMock(status_code=200)
        mock_resp.iter_content.return_value = [b"synced_video_bytes"]
        mock_resp.__enter__.return_value = mock_resp
        mock_get.return_value = mock_resp

        out_path = self.temp_dir / "synced.mp4"
        client = SyncLabsClient(api_key="sync_key")
        res_file = client.download_result("https://storage.sync.so/output.mp4", out_path)

        self.assertTrue(res_file.exists())
        self.assertEqual(res_file.read_bytes(), b"synced_video_bytes")


class TestIntervalSelection(unittest.TestCase):
    def test_empty_cues_entire_video_passthrough(self):
        cues = []
        scenes = [{"start": 0.0, "end": 10.0}]
        timeline = select_speech_intervals(cues, scenes, total_duration_sec=10.0)

        self.assertEqual(len(timeline), 1)
        self.assertFalse(timeline[0]["is_speech"])
        self.assertEqual(timeline[0]["action"], "passthrough")
        self.assertEqual(timeline[0]["duration"], 10.0)

    def test_merges_close_cues_under_half_second(self):
        # Cue 1: 1.0s to 2.5s; Cue 2: 2.8s to 4.0s (0.3s pause -> should merge)
        cues = [
            Cue(id=1, start_ms=1000, end_ms=2500, text="first"),
            Cue(id=2, start_ms=2800, end_ms=4000, text="second"),
        ]
        scenes = [{"start": 0.0, "end": 10.0}]
        timeline = select_speech_intervals(cues, scenes, total_duration_sec=10.0, merge_gap_sec=0.5)

        speech = [s for s in timeline if s["is_speech"]]
        self.assertEqual(len(speech), 1)
        self.assertEqual(speech[0]["start"], 1.0)
        self.assertEqual(speech[0]["end"], 4.0)

    def test_keeps_distant_cues_separate(self):
        # Cue 1: 1.0s to 2.0s; Cue 2: 4.0s to 6.0s (2.0s pause -> separate)
        cues = [
            Cue(id=1, start_ms=1000, end_ms=2000, text="first"),
            Cue(id=2, start_ms=4000, end_ms=6000, text="second"),
        ]
        scenes = [{"start": 0.0, "end": 10.0}]
        timeline = select_speech_intervals(cues, scenes, total_duration_sec=10.0, merge_gap_sec=0.5)

        speech = [s for s in timeline if s["is_speech"]]
        self.assertEqual(len(speech), 2)
        self.assertEqual(speech[0]["start"], 1.0)
        self.assertEqual(speech[0]["end"], 2.0)
        self.assertEqual(speech[1]["start"], 4.0)
        self.assertEqual(speech[1]["end"], 6.0)

        passthrough = [s for s in timeline if not s["is_speech"]]
        # Should have: [0.0 - 1.0], [2.0 - 4.0], [6.0 - 10.0]
        self.assertEqual(len(passthrough), 3)

    def test_splits_speech_at_scene_cut(self):
        # Continuous speech from 1.0s to 5.0s, but camera cut at 3.0s
        cues = [
            Cue(id=1, start_ms=1000, end_ms=5000, text="talking across cut")
        ]
        scenes = [
            {"start": 0.0, "end": 3.0},
            {"start": 3.0, "end": 8.0}
        ]
        timeline = select_speech_intervals(cues, scenes, total_duration_sec=8.0)

        speech = [s for s in timeline if s["is_speech"]]
        self.assertEqual(len(speech), 2)
        self.assertEqual(speech[0]["start"], 1.0)
        self.assertEqual(speech[0]["end"], 3.0)
        self.assertEqual(speech[1]["start"], 3.0)
        self.assertEqual(speech[1]["end"], 5.0)


class TestDubbingPipelineEndToEnd(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.job_dir = self.temp_dir / "job_out"
        self.job_dir.mkdir(parents=True, exist_ok=True)

        self.video_path = self.temp_dir / "test_input.mp4"
        self.video_path.write_bytes(b"dummy source video")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("src.video_dubbing_pipeline.get_video_info")
    @patch("src.video_dubbing_pipeline.detect_scenes")
    @patch("src.video_dubbing_pipeline.extract_subclip")
    @patch("src.video_dubbing_pipeline.extract_audio_segment")
    @patch("src.video_dubbing_pipeline.assemble_segment")
    @patch("src.video_dubbing_pipeline.join_segments")
    @patch("src.video_dubbing_pipeline.mux_audio_video")
    def test_pipeline_with_approval_and_resumption(
        self,
        mock_mux,
        mock_concat,
        mock_standardize,
        mock_extract_audio,
        mock_extract_subclip,
        mock_detect_scenes,
        mock_video_info
    ):
        mock_standardize.side_effect = lambda src, audio, dst, *args, **kw: Path(dst).write_bytes(b"standardized clip") or dst
        mock_video_info.return_value = {
            "fps": 25.0,
            "width": 1280,
            "height": 720,
            "duration": 6.0,
            "frame_count": 150
        }
        mock_detect_scenes.return_value = [
            {"index": 0, "start": 0.0, "end": 3.0, "duration": 3.0},
            {"index": 1, "start": 3.0, "end": 6.0, "duration": 3.0}
        ]

        # Setup mocked Dubbing Client
        mock_dub = MagicMock()
        mock_dub.create_dub_job.return_value = "dub_abc_123"
        mock_dub.wait_for_completion.return_value = {"status": "dubbed"}

        def fake_download_transcript(dub_id, lang, path, format_type="srt"):
            Path(path).write_text("1\n00:00:01,000 --> 00:00:02,500\nSpeech cue\n", encoding="utf-8")
            return [Cue(1, 1000, 2500, "Speech cue")]

        def fake_download_audio(dub_id, lang, path):
            Path(path).write_bytes(b"fake dubbed audio mp3")

        mock_dub.download_transcript.side_effect = fake_download_transcript
        mock_dub.download_dubbed_audio.side_effect = fake_download_audio

        # Setup mocked Sync Labs Client
        mock_sync = MagicMock()
        mock_sync.upload_file.return_value = "https://storage.sync.so/asset.mp4"
        mock_sync.generate.return_value = {"id": "sync_gen_999"}
        mock_sync.wait_for_completion.return_value = {
            "id": "sync_gen_999",
            "status": "COMPLETED",
            "outputUrl": "https://storage.sync.so/output.mp4"
        }

        def fake_download_sync(url, path):
            Path(path).write_bytes(b"synced clip mp4")

        mock_sync.download_result.side_effect = fake_download_sync

        def fake_extract_subclip(vid, s, e, out, target_fps=25):
            Path(out).write_bytes(b"fake subclip")

        def fake_extract_audio(audio, s, e, out):
            Path(out).write_bytes(b"fake audio chunk")

        mock_extract_subclip.side_effect = fake_extract_subclip
        mock_extract_audio.side_effect = fake_extract_audio

        # Run 1: with auto_approve=True
        final_video, manifest = run_video_dubbing_pipeline(
            source_video_path=self.video_path,
            target_lang="es",
            job_dir=self.job_dir,
            auto_approve=True,
            dubbing_client=mock_dub,
            synclabs_client=mock_sync,
            poll_interval=0.01
        )

        self.assertIsNotNone(final_video)
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["elevenlabs_dubbing_id"], "dub_abc_123")
        self.assertEqual(mock_dub.create_dub_job.call_count, 1)
        self.assertEqual(mock_sync.generate.call_count, 1)

        # Run 2: Resumption test! Run again on the same job_dir.
        # It must NOT call create_dub_job or generate again!
        final_video_2, manifest_2 = run_video_dubbing_pipeline(
            source_video_path=self.video_path,
            target_lang="es",
            job_dir=self.job_dir,
            auto_approve=True,
            dubbing_client=mock_dub,
            synclabs_client=mock_sync,
            poll_interval=0.01
        )

        self.assertIsNotNone(final_video_2)
        # Call count must stay 1 because resumption skips completed calls!
        self.assertEqual(mock_dub.create_dub_job.call_count, 1)
        self.assertEqual(mock_sync.generate.call_count, 1)
        # Changing the model must not reuse the old generation.
        run_video_dubbing_pipeline(
            source_video_path=self.video_path, target_lang="es", job_dir=self.job_dir,
            auto_approve=True, dubbing_client=mock_dub, synclabs_client=mock_sync,
            sync_model="lipsync-2", poll_interval=0.01)
        self.assertEqual(mock_sync.generate.call_count, 2)
        self.assertEqual(mock_sync.generate.call_args.kwargs["model"], "lipsync-2")


    @patch("builtins.input", return_value="n")
    @patch("src.video_dubbing_pipeline.get_video_info")
    @patch("src.video_dubbing_pipeline.detect_scenes")
    def test_pipeline_cancelled_by_user_without_auto_approve(
        self,
        mock_detect_scenes,
        mock_video_info,
        mock_input
    ):
        mock_video_info.return_value = {
            "fps": 25.0,
            "width": 1280,
            "height": 720,
            "duration": 5.0,
            "frame_count": 125
        }
        mock_detect_scenes.return_value = [{"start": 0.0, "end": 5.0}]

        mock_dub = MagicMock()
        mock_dub.create_dub_job.return_value = "dub_123"
        mock_dub.wait_for_completion.return_value = {"status": "dubbed"}

        def fake_download_transcript(dub_id, lang, path, format_type="srt"):
            Path(path).write_text("1\n00:00:01,000 --> 00:00:03,000\nSpeech\n", encoding="utf-8")
            return [Cue(1, 1000, 3000, "Speech")]

        def fake_download_audio(dub_id, lang, path):
            Path(path).write_bytes(b"audio")

        mock_dub.download_transcript.side_effect = fake_download_transcript
        mock_dub.download_dubbed_audio.side_effect = fake_download_audio

        mock_sync = MagicMock()

        final_video, manifest = run_video_dubbing_pipeline(
            source_video_path=self.video_path,
            target_lang="es",
            job_dir=self.job_dir,
            auto_approve=False,
            dubbing_client=mock_dub,
            synclabs_client=mock_sync,
            poll_interval=0.01
        )

        self.assertIsNone(final_video)
        self.assertEqual(manifest["status"], "pending_user_approval")
        # Ensure Sync Labs was never called!
        self.assertEqual(mock_sync.generate.call_count, 0)


class TestVoiceoverAwareDubbingPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.talking_video = self.temp_dir / "talking_head.mp4"
        self.silent_video = self.temp_dir / "silent_head.mp4"
        self.product_video = self.temp_dir / "product.mp4"

        # 1. Create talking head video with moving mouth
        self._write_video(self.talking_video, moving_mouth=True, has_face=True)
        # 2. Create silent pose head video with static mouth
        self._write_video(self.silent_video, moving_mouth=False, has_face=True)
        # 3. Create product/cutaway video with no face
        self._write_video(self.product_video, moving_mouth=False, has_face=False)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_video(self, output_path, moving_mouth=True, has_face=True, fps=25.0, duration=2.0):
        width, height = 320, 240
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
        total_frames = int(duration * fps)

        for f_idx in range(total_frames):
            frame = np.full((height, width, 3), 200, dtype=np.uint8)
            if has_face:
                # Face oval in natural skin tone
                cv2.ellipse(frame, (160, 120), (50, 65), 0, 0, 360, (140, 160, 220), -1)
                cv2.circle(frame, (140, 100), 6, (40, 40, 40), -1)
                cv2.circle(frame, (180, 100), 6, (40, 40, 40), -1)
                if moving_mouth:
                    mouth_h = int(2 + 18 * abs(np.sin(f_idx * 1.2)))
                else:
                    mouth_h = 8
                cv2.ellipse(frame, (160, 150), (16, mouth_h), 0, 0, 360, (50, 50, 160), -1)
            else:
                # B-roll green product bottle
                frame[:] = (40, 40, 80)
                cv2.rectangle(frame, (130, 60), (190, 200), (0, 220, 100), -1)
            out.write(frame)
        out.release()

    def test_classify_voiceover_aware_no_face_is_broll(self):
        res = classify_shot_voiceover_aware(self.product_video, 0.0, 2.0)
        self.assertEqual(res["type"], "b_roll")
        self.assertEqual(res["action"], "passthrough")
        self.assertIn("No face detected", res["reason"])

    def test_classify_voiceover_aware_low_mouth_motion_is_broll(self):
        res = classify_shot_voiceover_aware(self.silent_video, 0.0, 2.0, motion_threshold=5.0)
        self.assertEqual(res["type"], "b_roll")
        self.assertEqual(res["action"], "passthrough")
        self.assertIn("Mouth motion below speaking threshold", res["reason"])

    def test_classify_voiceover_aware_articulating_mouth_is_aroll(self):
        res = classify_shot_voiceover_aware(self.talking_video, 0.0, 2.0, motion_threshold=5.0)
        self.assertEqual(res["type"], "a_roll")
        self.assertEqual(res["action"], "sync")
        self.assertIn("Talking head confirmed", res["reason"])

    def test_auto_detect_creator_anchor(self):
        scenes = [{"start": 0.0, "end": 2.0, "duration": 2.0}]
        anchor = auto_detect_creator_anchor(self.talking_video, scenes)
        self.assertIsNotNone(anchor, "Should extract anchor from talking head video")



class TestFrameAccurateExtraction(unittest.TestCase):
    """Regression tests for the frame-accurate extraction and PTS normalization fixes.

    These tests verify that:
    - extract_subclip converts float boundaries to integer frame numbers.
    - standardize_video_stream transcodes with setpts (not -c:v copy).
    - Frame count warnings are issued when the clip deviates from expected.
    """

    @patch("src.scene_analyzer.subprocess.run")
    def test_extract_subclip_uses_frame_boundary_seek_and_trim(self, mock_run):
        """extract_subclip must use -ss at a frame-aligned timestamp, and a
        ``fps=N,trim=end_frame=M,setpts=PTS-STARTPTS`` video filter chain."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "clip.mp4"
            from src.scene_analyzer import extract_subclip
            extract_subclip("/fake/video.mp4", 5.589, 9.343, out, target_fps=24000/1001)

        call_args = mock_run.call_args[0][0]
        # -ss must be present and express a frame-aligned float timestamp
        ss_idx = call_args.index("-ss")
        ss_val = float(call_args[ss_idx + 1])
        # frame 134 at 24000/1001 fps = 134 * 1001/24000 ≈ 5.5887 (< 5.589)
        self.assertAlmostEqual(ss_val, round(5.589 * (24000 / 1001)) / (24000 / 1001), places=2)

        # -vf must be present and include trim=end_frame=... and setpts=PTS-STARTPTS
        vf_idx = call_args.index("-vf")
        vf_val = call_args[vf_idx + 1]
        self.assertIn("trim=end_frame=", vf_val)
        self.assertIn("setpts=PTS-STARTPTS", vf_val)

        # -t must NOT be present (we use -vframes / trim instead)
        self.assertNotIn("-t", call_args)

    @patch("src.scene_analyzer.subprocess.run")
    def test_extract_subclip_zero_length_raises(self, mock_run):
        """Zero-length or reversed intervals must raise PipelineError."""
        from src.scene_analyzer import extract_subclip
        from src.common import PipelineError
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "clip.mp4"
            with self.assertRaises(PipelineError):
                extract_subclip("/fake/video.mp4", 5.0, 5.0, out, target_fps=25)

    @patch("src.video_dubbing_pipeline.subprocess.run")
    def test_standardize_uses_transcode_not_copy(self, mock_run):
        """standardize_video_stream must transcode (not -c:v copy) and apply setpts."""
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="{}")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "seg.mp4"
            src.write_bytes(b"fake mp4")
            dst = Path(tmp) / "std.mp4"
            from src.video_dubbing_pipeline import standardize_video_stream
            standardize_video_stream(str(src), str(dst))

        call_args = mock_run.call_args_list[0][0][0]
        # Must include -vf setpts=PTS-STARTPTS
        self.assertIn("-vf", call_args)
        vf_idx = call_args.index("-vf")
        self.assertIn("setpts=PTS-STARTPTS", call_args[vf_idx + 1])
        # Must NOT use -c:v copy
        self.assertNotIn("copy", call_args)

    @patch("src.video_dubbing_pipeline.subprocess.run")
    def test_standardize_warns_on_frame_count_mismatch(self, mock_run):
        """A warning should be printed when actual frame count != expected_frames."""
        import json

        # First call: ffmpeg transcode (success)
        # Second call: ffprobe (returns different frame count)
        fake_probe_out = json.dumps({
            "streams": [{"codec_type": "video", "nb_frames": "45"}]
        })
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr=""),           # ffmpeg encode
            MagicMock(returncode=0, stdout=fake_probe_out, stderr=""),  # ffprobe
        ]
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "seg.mp4"
            src.write_bytes(b"fake mp4")
            dst = Path(tmp) / "std.mp4"
            from src.video_dubbing_pipeline import standardize_video_stream
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                standardize_video_stream(str(src), str(dst), expected_frames=50)
            output = buf.getvalue()

        self.assertIn("Warning", output)
        self.assertIn("50", output)   # expected
        self.assertIn("45", output)   # actual


if __name__ == "__main__":
    unittest.main()
