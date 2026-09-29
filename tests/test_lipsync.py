import unittest
import numpy as np
import cv2
from pathlib import Path
import tempfile
import shutil

from src.scene_analyzer import get_video_info, detect_scenes, extract_subclip, concat_segments, mux_audio_video
from src.face_tracker import (
    detect_faces,
    compute_skin_ratio,
    compute_face_signature,
    compare_face_signatures,
    classify_shot
)
from src.video_dubbing import run_video_dubbing


def create_synthetic_test_video(output_path, duration_sec=4, fps=25, with_face_at=(0, 2)):
    """
    Creates a synthetic video that alternates between an A-roll shot (with drawn face)
    and a B-roll shot (e.g. solid color or non-face geometric objects / product mockup).
    """
    width, height = 320, 240
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    total_frames = int(duration_sec * fps)
    for frame_idx in range(total_frames):
        t = frame_idx / fps
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        # Shot 1: A-roll (simulated talking face with natural skin tone)
        if with_face_at[0] <= t < with_face_at[1]:
            frame[:] = (200, 200, 200) # light background
            # Draw head / face oval in skin tone (BGR: approx ~140, 160, 220)
            center = (160, 120)
            axes = (50, 65)
            cv2.ellipse(frame, center, axes, 0, 0, 360, (140, 160, 220), -1)
            # Eyes
            cv2.circle(frame, (140, 100), 6, (40, 40, 40), -1)
            cv2.circle(frame, (180, 100), 6, (40, 40, 40), -1)
            # Mouth
            cv2.ellipse(frame, (160, 150), (16, 8), 0, 0, 360, (50, 50, 160), -1)
        else:
            # Shot 2: B-roll (product mockup / drink bottle / mannequin)
            # Different background and bright neon green drink bottle
            frame[:] = (40, 40, 80)
            cv2.rectangle(frame, (130, 60), (190, 200), (0, 220, 100), -1)
            cv2.putText(frame, "B-ROLL", (100, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        out.write(frame)
    out.release()
    return output_path


def create_synthetic_audio(output_path, duration_sec=4, sample_rate=24000):
    import wave
    import struct
    n_samples = int(duration_sec * sample_rate)
    with wave.open(str(output_path), 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for i in range(n_samples):
            # simple sine tone
            value = int(32767.0 * 0.2 * np.sin(2.0 * np.pi * 440.0 * i / sample_rate))
            wav_file.writeframes(struct.pack('<h', value))
    return output_path


class TestLipSyncPipeline(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.video_path = self.temp_dir / "test_source.mp4"
        self.audio_path = self.temp_dir / "test_audio.wav"
        create_synthetic_test_video(self.video_path, duration_sec=4, fps=25, with_face_at=(0, 2))
        create_synthetic_audio(self.audio_path, duration_sec=4)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_video_info(self):
        info = get_video_info(self.video_path)
        self.assertEqual(info["width"], 320)
        self.assertEqual(info["height"], 240)
        self.assertAlmostEqual(info["duration"], 4.0, delta=0.2)

    def test_scene_detection(self):
        scenes = detect_scenes(self.video_path, threshold=20.0, min_scene_len_sec=0.5)
        self.assertGreaterEqual(len(scenes), 2, "Should detect at least 2 shots (A-roll face vs B-roll product)")
        print(f"\n[Test] Detected {len(scenes)} scenes: {scenes}")

    def test_skin_ratio_computation(self):
        # Synthetic skin crop
        skin_img = np.full((100, 100, 3), (140, 160, 220), dtype=np.uint8)
        ratio = compute_skin_ratio(skin_img)
        self.assertGreater(ratio, 0.8, "Natural skin tone should have high skin ratio")

        # Synthetic green bottle (B-roll)
        bottle_img = np.full((100, 100, 3), (0, 220, 100), dtype=np.uint8)
        ratio_bottle = compute_skin_ratio(bottle_img)
        self.assertLess(ratio_bottle, 0.1, "Green bottle should have near zero skin ratio")

    def test_face_signature_matching(self):
        face1 = np.full((100, 100, 3), (140, 160, 220), dtype=np.uint8)
        face2 = np.full((100, 100, 3), (135, 155, 215), dtype=np.uint8)
        other = np.full((100, 100, 3), (200, 50, 50), dtype=np.uint8)

        sig1 = compute_face_signature(face1)
        sig2 = compute_face_signature(face2)
        sig_other = compute_face_signature(other)

        sim_same = compare_face_signatures(sig1, sig2)
        sim_other = compare_face_signatures(sig1, sig_other)

        self.assertGreater(sim_same, 0.85, "Similar character face signatures should correlate strongly")
        self.assertLess(sim_other, sim_same, "Different color signature should have lower correlation")

    def test_b_roll_classification(self):
        # Shot 2 is between 2.0s and 4.0s (B-roll product without face)
        b_roll_class = classify_shot(self.video_path, start_sec=2.2, end_sec=3.8)
        self.assertEqual(b_roll_class["type"], "b_roll", "Product shot must be classified as B-roll")
        self.assertIn("No face detected", b_roll_class["reason"])

    def test_full_video_dubbing_dry_run(self):
        job_dir = self.temp_dir / "job_out"
        final_video, manifest = run_video_dubbing(
            source_video_path=self.video_path,
            master_audio_path=self.audio_path,
            job_dir=job_dir,
            dry_run=True,
            scene_threshold=20.0
        )
        self.assertTrue(Path(final_video).exists(), "Final video file must be generated")
        self.assertGreater(Path(final_video).stat().st_size, 1000)
        self.assertGreaterEqual(manifest["b_roll_count"], 1, "Must recognize at least one B-roll shot")
        print(f"\n[Test] Video Dubbing Completed: {final_video}")
        print(f"[Test] Manifest Summary: Shots={manifest['shots_count']}, A-roll={manifest['a_roll_count']}, B-roll={manifest['b_roll_count']}")


if __name__ == "__main__":
    unittest.main()

