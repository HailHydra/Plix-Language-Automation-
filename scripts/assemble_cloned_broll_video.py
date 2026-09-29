import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dub_assembly import assemble_segment, join_segments
from src.scene_analyzer import get_video_info
from src.common import read_json

def main():
    base_dir = Path(r"output\dub_WhatsApp Video 2026-09-28 at 6.01.20 PM_en")
    source_video = Path(r"input\WhatsApp Video 2026-09-28 at 6.01.20 PM.mp4")
    seg_dir = base_dir / "segments"
    manifest = read_json(base_dir / "dub_manifest.json")

    fps = 23.976023976023978
    total_frames = 542

    print("Source video info:", get_video_info(source_video))

    # Timeline in manifest has 15 items:
    # 0: start 0.0 - 0.16 (frames 0 to 4 -> 4 frames)
    # 1: 0.16 - 2.085 (frames 4 to 50 -> 46 frames)
    # 2: 2.085 - 4.004 (frames 50 to 96 -> 46 frames)
    # 3: 4.004 - 5.589 (frames 96 to 134 -> 38 frames)
    # Together 0..3: 134 frames (0.0 to 5.589s)
    #
    # We will assemble Segments 0..3 with our cloned fitted audio broll_fitted_voiceover.wav:
    # Audio starts at 0.0, so:
    # Seg 0 (0 to 4 frames, dur 0.16s): audio_start = 0.0
    # Seg 1 (4 to 50 frames, 46 frames, start 0.16s): audio_start = 4 / fps = 0.166833s
    # Seg 2 (50 to 96 frames, 46 frames, start 2.085s): audio_start = 50 / fps = 2.085417s
    # Seg 3 (96 to 134 frames, 38 frames, start 4.004s): audio_start = 96 / fps = 4.004000s

    broll_audio = base_dir / "broll_fitted_voiceover.wav"

    # Assemble Seg 0, 1, 2, 3
    assembled_segments = []
    
    seg0_raw = seg_dir / "seg_000_d3f0665279f3e0ae_raw.mp4"
    if not seg0_raw.exists(): seg0_raw = seg_dir / "seg_000_raw.mp4"
    p0 = assemble_segment(seg0_raw, broll_audio, seg_dir / "seg_000_cloned.mov", 4, fps, audio_start=0.0)
    assembled_segments.append(p0)

    seg1_raw = seg_dir / "seg_001_44d8e50b14eaaed3_raw.mp4"
    if not seg1_raw.exists(): seg1_raw = seg_dir / "seg_001_raw.mp4"
    p1 = assemble_segment(seg1_raw, broll_audio, seg_dir / "seg_001_cloned.mov", 46, fps, audio_start=4 / fps)
    assembled_segments.append(p1)

    seg2_raw = seg_dir / "seg_002_fae94dc9bf2ff292_raw.mp4"
    if not seg2_raw.exists(): seg2_raw = seg_dir / "seg_002_raw.mp4"
    p2 = assemble_segment(seg2_raw, broll_audio, seg_dir / "seg_002_cloned.mov", 46, fps, audio_start=50 / fps)
    assembled_segments.append(p2)

    seg3_raw = seg_dir / "seg_003_3b11908308a23c41_raw.mp4"
    if not seg3_raw.exists(): seg3_raw = seg_dir / "seg_003_raw.mp4"
    p3 = assemble_segment(seg3_raw, broll_audio, seg_dir / "seg_003_cloned.mov", 38, fps, audio_start=96 / fps)
    assembled_segments.append(p3)

    # Segment 4: Talking Head (Sync Labs output: seg_004_b1b29f07419cf312_synced.mp4, 90 frames: 134 to 224)
    seg4_synced = seg_dir / "seg_004_b1b29f07419cf312_synced.mp4"
    if not seg4_synced.exists(): seg4_synced = seg_dir / "seg_004_0635230d28dddf48_synced.mp4"
    # Seg 4 has its own synced audio inside the file
    p4 = assemble_segment(seg4_synced, seg4_synced, seg_dir / "seg_004_cloned.mov", 90, fps, audio_start=0.0)
    assembled_segments.append(p4)

    # Segments 5 to 14: use already assembled .mov files from manifest
    for i in range(5, 15):
        orig_mov = list(seg_dir.glob(f"seg_{i:03d}_*_paired.mov"))
        if not orig_mov:
            raise RuntimeError(f"Missing paired mov for segment {i}")
        assembled_segments.append(orig_mov[0])

    print(f"Total segments to join: {len(assembled_segments)}")
    for i, seg in enumerate(assembled_segments):
        info = get_video_info(seg)
        print(f"  Seg #{i:02d}: {info['frame_count']} frames ({info['duration']:.3f}s) - {seg.name}")

    final_output = base_dir / "final_hybrid_cloned_dubbed_en.mp4"
    join_segments(assembled_segments, final_output, total_frames, fps)

    print("\n=======================================================")
    print(f"SUCCESS! Master Dubbed Video created at:\n{final_output}")
    print("=======================================================")

    final_info = get_video_info(final_output)
    print("Final Video Info:", final_info)

if __name__ == "__main__":
    main()
