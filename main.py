import argparse
import os
from pathlib import Path
import sys

# Force UTF-8 output so non-ASCII (Devanagari, CJK, etc.) prints correctly on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.common import PipelineError, load_env
from src.pipeline import prepare, render, edit_segment

ROOT = Path(__file__).resolve().parent


def main():
    load_env(ROOT / ".env")
    parser = argparse.ArgumentParser(description="SRT to synchronized speech with separate input/output directories.")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── prepare / render / edit (original SRT-to-audio pipeline) ─────────────
    p = sub.add_parser("prepare", help="Validate and translate without generating speech.")
    p.add_argument("srt", type=Path)
    p.add_argument("--source", default="en", help="Source language code (default en). auto requires a detection provider.")
    p.add_argument("--target", required=True)
    p.add_argument("--provider", choices=["none", "libre"], default="none")
    inputs = p.add_mutually_exclusive_group()
    inputs.add_argument("--translations", type=Path, help="Reviewed JSON mapping cue IDs to target text.")
    inputs.add_argument("--bilingual", action="store_true", help="Source and translation in each SRT cue.")
    inputs.add_argument("--translated-srt", type=Path, help="Separate translated SRT with matching timestamps.")
    p.add_argument("--source-lines", type=int, default=1, help="Source lines per bilingual cue; remaining lines are translated text.")
    p.add_argument("--target-first", action="store_true", help="Translated lines precede source lines in bilingual cues.")
    p.add_argument("--source-label", help="Exact source label, e.g. English, in [English]: text.")
    p.add_argument("--target-label", help="Exact target label, e.g. Marathi, in [Marathi]: text.")
    p.add_argument("--locale")
    p.add_argument("--output", type=Path, default=ROOT / "output")

    r = sub.add_parser("render", help="Generate or resume speech, verify timing and export.")
    r.add_argument("job", type=Path)
    r.add_argument("--voice", required=True)
    r.add_argument("--model", required=True)
    r.add_argument("--max-speed", type=float, default=1.10)
    r.add_argument("--mp3", action="store_true")

    e = sub.add_parser("edit", help="Edit or selectively regenerate a cue.")
    e.add_argument("job", type=Path)
    e.add_argument("--id", type=int, required=True)
    e.add_argument("--text")
    e.add_argument("--skip", choices=["yes", "no"])
    e.add_argument("--regenerate", action="store_true")

    # ── lipsync (legacy HuggingFace ZeroGPU) ─────────────────────────────────
    ls = sub.add_parser("lipsync", help="Character-locked, B-roll aware video lip-sync via free Hugging Face ZeroGPU.")
    ls.add_argument("--video", type=Path, required=True, help="Path to source video (.mp4).")
    ls.add_argument("--audio", type=Path, help="Path to synchronized/fitted master audio (.wav). Optional if --job is provided.")
    ls.add_argument("--job", type=Path, help="Job directory containing exported audio or to store video segments.")
    ls.add_argument("--reference", type=Path, help="Optional reference photo of the main character for character-locking.")
    ls.add_argument("--dry-run", action="store_true", help="Simulate pipeline locally (test B-roll detection & stitching without cloud delays).")
    ls.add_argument("--space", type=str, help="Hugging Face Space name to use (default: fffiloni/LatentSync).")

    # ── export-aroll / assemble (legacy Colab LatentSync workflow) ───────────
    p_exp = sub.add_parser("export-aroll", help="Extract only speaking A-Roll clips for fast high-res Colab LatentSync.")
    p_exp.add_argument("--video", type=Path, required=True)
    p_exp.add_argument("--audio", type=Path, required=True)
    p_exp.add_argument("--job", type=Path)

    p_asm = sub.add_parser("assemble", help="Assemble high-res synced clip with original B-roll shots.")
    p_asm.add_argument("--job", type=Path, required=True)
    p_asm.add_argument("--synced", type=Path, required=True)

    # ── dub (legacy pipeline — kept for backwards compatibility) ─────────────
    dub_p = sub.add_parser("dub", help="Legacy dubbing pipeline via ElevenLabs and Sync Labs.")
    dub_p.add_argument("--video", type=Path, required=True)
    dub_p.add_argument("--target-lang", "--target", dest="target_lang", required=True)
    dub_p.add_argument("--source-lang", "--source", dest="source_lang", default="auto")
    dub_p.add_argument("--job", type=Path)
    dub_p.add_argument("--sync-model", default=os.environ.get("SYNC_MODEL", "lipsync-2-pro"))
    dub_p.add_argument("--broll-model", choices=["lipsync-2", "lipsync-2-pro"], default="lipsync-2")
    dub_p.add_argument("--broll-audio", type=Path)
    dub_p.add_argument("--num-speakers", type=int, default=0)
    dub_p.add_argument("--auto-approve", "--yes", "-y", dest="auto_approve", action="store_true")
    dub_p.add_argument("--dry-run", action="store_true")
    dub_p.add_argument("--scene-threshold", type=float, default=32.0)
    dub_p.add_argument("--broll-filter", action=argparse.BooleanOptionalAction, default=True)
    dub_p.add_argument("--hybrid-clone", action="store_true")
    dub_p.add_argument("--reference", type=Path)
    dub_p.add_argument("--target-frame", type=float)
    dub_p.add_argument("--target-point", nargs=2, type=int, metavar=("X", "Y"))
    dub_p.add_argument("--reviewed-audio", type=Path)
    dub_p.add_argument("--reviewed-transcript", type=Path)
    dub_p.add_argument("--motion-threshold", type=float, default=5.0)

    # ── dub2 (NEW 5-stage pipeline) ───────────────────────────────────────────
    dub2 = sub.add_parser(
        "dub2",
        help=(
            "[NEW] 5-stage pipeline: "
            "1) Whisper transcript  "
            "2) Scene classify (YuNet+SFace)  "
            "3) ElevenLabs Dubbing (full-video, creator voice preserved)  "
            "4) Sync Labs lipsync on A-Roll only  "
            "5) Frame-locked stitch"
        ),
    )
    dub2.add_argument("--video", type=Path, required=True, help="Source video (.mp4).")
    dub2.add_argument("--target", required=True,
                      help="Target language code (e.g. mr=Marathi, hi=Hindi, en=English).")
    dub2.add_argument("--source", default="auto",
                      help="Source language code (default auto-detect).")
    dub2.add_argument("--job", type=Path,
                      help="Job directory; auto-named 'output/dub2_{stem}_{lang}' if omitted.")
    dub2.add_argument("--sync-model", default=os.environ.get("SYNC_MODEL", "lipsync-2-pro"),
                      help="Sync Labs model (default lipsync-2-pro).")
    dub2.add_argument("--scene-threshold", type=float, default=32.0,
                      help="Camera cut detection sensitivity (default 32.0; lower=more cuts).")
    dub2.add_argument("--target-frame", type=float,
                      help="Timestamp (seconds) in video clearly showing the target speaker.")
    dub2.add_argument("--target-point", nargs=2, type=int, metavar=("X", "Y"),
                      help="Pixel (x y) inside target speaker's face at --target-frame.")
    dub2.add_argument("--reference", type=Path,
                      help="Reference photo of the target speaker for identity anchor.")
    dub2.add_argument("--transcript", type=Path,
                      help="Pre-made source SRT to skip Stage 1 Whisper transcription.")
    dub2.add_argument("--num-speakers", type=int, default=0,
                      help="Expected speaker count for ElevenLabs (0 = auto-detect).")
    dub2.add_argument("--dry-run", action="store_true",
                      help="Simulate full pipeline without paying for ElevenLabs or Sync Labs.")
    dub2.add_argument("--skip", type=int, nargs="*", metavar="STAGE",
                      help="Skip specific stages (reuse cached output). E.g. --skip 1 3")
    # ─────────────────────────────────────────────────────────────────────────

    args = parser.parse_args()
    try:
        # ── export-aroll ──────────────────────────────────────────────────────
        if args.command == "export-aroll":
            from src.video_dubbing import export_aroll_package
            job_dir = args.job or ROOT / "output" / f"colab_pkg_{args.video.stem}"
            export_aroll_package(args.video, args.audio, job_dir)
            print(f"\nUpload the extracted A-Roll video and audio to Colab for instant 1080p diffusion sync!")
            return 0

        # ── assemble ──────────────────────────────────────────────────────────
        if args.command == "assemble":
            from src.video_dubbing import assemble_from_synced
            output_vid = assemble_from_synced(args.job, args.synced)
            print(f"\nFinal Assembled Studio Video: {output_vid}")
            return 0

        # ── lipsync ───────────────────────────────────────────────────────────
        if args.command == "lipsync":
            from src.video_dubbing import run_video_dubbing
            audio_path = args.audio
            job_dir = args.job
            if audio_path is None:
                if job_dir and (job_dir / "exports" / "fitted.wav").exists():
                    audio_path = job_dir / "exports" / "fitted.wav"
                elif job_dir and (job_dir / "combined_fitted.wav").exists():
                    audio_path = job_dir / "combined_fitted.wav"
                else:
                    raise PipelineError("Must specify --audio <path> or provide --job with fitted.wav.")
            if job_dir is None:
                job_dir = ROOT / "output" / f"video_{args.video.stem}"
            final_video, manifest = run_video_dubbing(
                source_video_path=args.video,
                master_audio_path=audio_path,
                job_dir=job_dir,
                reference_image_path=args.reference,
                dry_run=args.dry_run,
                space_name=args.space,
            )
            print(f"\nFinal lip-synced video: {final_video}")
            return 0

        # ── dub (legacy) ──────────────────────────────────────────────────────
        if args.command == "dub":
            if getattr(args, "hybrid_clone", False):
                from src.hybrid_clone import run_hybrid_clone
                out = run_hybrid_clone(
                    source_video_path=args.video,
                    target_lang=args.target_lang,
                    job_dir=args.job,
                    sync_model=args.sync_model,
                    dry_run=args.dry_run,
                )
                print(f"\nFinal Hybrid Cloned Video: {out}")
                return 0
            from src.video_dubbing_pipeline import run_video_dubbing_pipeline
            final_vid, manifest = run_video_dubbing_pipeline(
                source_video_path=args.video,
                target_lang=args.target_lang,
                source_lang=args.source_lang,
                job_dir=args.job,
                num_speakers=args.num_speakers,
                sync_model=args.sync_model,
                broll_model=args.broll_model,
                broll_audio=args.broll_audio,
                auto_approve=args.auto_approve,
                dry_run=args.dry_run,
                scene_threshold=args.scene_threshold,
                broll_filter=args.broll_filter,
                reference_image=args.reference,
                target_frame=args.target_frame,
                target_point=args.target_point,
                reviewed_audio=args.reviewed_audio,
                reviewed_transcript=args.reviewed_transcript,
                motion_threshold=args.motion_threshold,
            )
            if final_vid:
                print(f"\nDubbing completed successfully: {final_vid}")
                return 0
            return 2

        # ── dub2 (NEW 5-stage pipeline) ───────────────────────────────────────
        if args.command == "dub2":
            from src.engine import run_dubbing_engine
            target_point = tuple(args.target_point) if args.target_point else None
            final_video = run_dubbing_engine(
                source_video_path=args.video,
                target_lang=args.target,
                source_lang=args.source,
                job_dir=args.job,
                sync_model=args.sync_model,
                scene_threshold=args.scene_threshold,
                target_frame=args.target_frame,
                target_point=target_point,
                reference_image=args.reference,
                supplied_transcript=args.transcript,
                num_speakers=args.num_speakers,
                dry_run=args.dry_run,
                skip_stages=args.skip or [],
            )
            print(f"\n✓ Final dubbed video: {final_video}")
            return 0

        # ── prepare ───────────────────────────────────────────────────────────
        if args.command == "prepare":
            job = prepare(
                args.srt, args.output, args.source, args.target,
                args.provider, args.translations, args.locale,
                bilingual=args.bilingual, source_lines=args.source_lines,
                source_first=not args.target_first, translated_srt=args.translated_srt,
                source_label=args.source_label, target_label=args.target_label,
            )
            print(f"Prepared: {job}\nReview manifest.json, then run render.")
            return 0

        # ── edit ──────────────────────────────────────────────────────────────
        if args.command == "edit":
            edit_segment(args.job, args.id, args.text,
                         None if args.skip is None else args.skip == "yes", args.regenerate)
            print("Saved. Render again to reuse unchanged cached segments.")
            return 0

        # ── render ────────────────────────────────────────────────────────────
        result = render(
            args.job, args.voice, args.model, args.max_speed, args.mp3,
            lambda n, total, status: print(f"{n}/{total}: {status}", flush=True),
        )
        print(f"Status: {result['status']}")
        for kind, path in result["exports"].items():
            print(f"{kind}: {path}")
        if result.get("error"):
            print(result["error"], file=sys.stderr)
        return 0 if result["status"] == "ready_for_listening_review" else 2

    except (PipelineError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
