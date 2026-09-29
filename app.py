"""Local review UI. Launch: python -m streamlit run app.py"""
from pathlib import Path
import uuid
import streamlit as st
from src.common import load_env, read_json, PipelineError
from src.pipeline import prepare, render, edit_segment

ROOT = Path(__file__).resolve().parent
load_env(ROOT / ".env")

try:
    import pandas as _pd
    HAS_PANDAS = True
except (ImportError, Exception):
    HAS_PANDAS = False
st.set_page_config(page_title="Text to Audio", layout="wide")
st.title("Text to Audio")
st.caption("Use your translated subtitles to generate speech that fits the timeline.")

with st.expander("Create a job", expanded="job" not in st.session_state):
    upload = st.file_uploader("Source subtitles", type=["srt"])
    left, right = st.columns(2)
    source = left.text_input("Source language code", value="en")
    target = right.text_input("Target language code", value="ml")
    layout = st.selectbox("Subtitle layout", [
        "Bilingual SRT", "Separate source and translated SRTs",
        "Target-language SRT only", "Source SRT + translation JSON",
        "Translate source SRT (LibreTranslate)",
    ])
    translated = None
    source_lines, source_first = 1, True
    source_label, target_label = None, None
    if layout == "Bilingual SRT":
        labeled = st.checkbox("Text has language labels, such as [English]: and [Marathi]:")
        if labeled:
            source_label = st.text_input("Source label in file", value="English")
            target_label = st.text_input("Target label in file", value="Marathi")
            st.caption("Labels select the script and are removed before speech. For Marathi, set the target language code to mr.")
        order = st.radio("Line order in each subtitle", ["Source first", "Translation first"], horizontal=True)
        source_first = order == "Source first"
        source_lines = int(st.number_input("Source lines per subtitle", min_value=1, value=1, step=1))
        st.caption("Remaining lines are the translation. Check the imported target text before generating speech. No translation API is needed.")
    elif layout == "Separate source and translated SRTs":
        translated = st.file_uploader("Translated subtitles", type=["srt"])
        st.caption("Both files must have matching cue counts and timestamps. No translation API is needed.")
    elif layout == "Source SRT + translation JSON":
        translated = st.file_uploader("Reviewed translations (JSON keyed by cue ID)", type=["json"])
    elif layout == "Target-language SRT only":
        st.caption("All subtitle text is spoken in the target language; the source-language field is ignored.")
    else:
        st.caption("Requires a configured LibreTranslate server and a supported language pair.")
    missing_translation = layout in ("Separate source and translated SRTs", "Source SRT + translation JSON") and translated is None
    if st.button("Prepare text", disabled=upload is None or missing_translation):
        try:
            input_dir = ROOT / "input" / uuid.uuid4().hex[:12]
            input_dir.mkdir(parents=True)
            path = input_dir / "source.srt"
            path.write_bytes(upload.getvalue())
            translation_path, translated_srt = None, None
            if translated is not None:
                if layout == "Separate source and translated SRTs":
                    translated_srt = input_dir / "translated.srt"
                    translated_srt.write_bytes(translated.getvalue())
                else:
                    translation_path = input_dir / "translations.json"
                    translation_path.write_bytes(translated.getvalue())
            with st.spinner("Preparing text"):
                job = prepare(path, ROOT / "output",
                              target if layout == "Target-language SRT only" else source, target,
                              "libre" if layout == "Translate source SRT (LibreTranslate)" else "none",
                              translation_path, bilingual=layout == "Bilingual SRT",
                              source_lines=source_lines, source_first=source_first,
                              translated_srt=translated_srt,
                              source_label=source_label, target_label=target_label)
            st.session_state.job = str(job)
        except (PipelineError, OSError, ValueError) as error:
            st.error(str(error))

jobs = sorted(p for p in (ROOT / "output").glob("*") if (p / "manifest.json").exists())
if jobs:
    current = st.session_state.get("job")
    names = [str(p) for p in jobs]
    selected = st.selectbox("Saved job", names, index=names.index(current) if current in names else len(names) - 1)
    st.session_state.job = selected
    job = Path(selected)
    manifest = read_json(job / "manifest.json")
    st.subheader(f"Text review · {manifest['source_language']} → {manifest['target_language']}")
    st.write("Status:", manifest["status"])
    for segment in manifest["segments"]:
        with st.expander(f"Cue {segment['id']} · {segment['available_ms'] / 1000:.2f}s · {segment['status']}"):
            st.write("Source:", segment["source_text"])
            st.caption("Context: " + " / ".join(segment["context"]))
            if segment["non_speech_candidate"]:
                st.info("This may be a non-speech caption. Review whether to skip it.")
            with st.form(f"{job.name}-{segment['id']}"):
                text = st.text_area("Target text", value=segment["target_text"])
                skip = st.checkbox("Skip this caption", value=segment["skip"])
                regenerate = st.checkbox("Generate a fresh take on the next render")
                if st.form_submit_button("Save cue"):
                    try:
                        edit_segment(job, segment["id"], text, skip, regenerate)
                        st.rerun()
                    except (PipelineError, OSError, ValueError) as error:
                        st.error(str(error))
            if segment.get("audio") and Path(segment["audio"]).exists():
                st.audio(Path(segment["audio"]).read_bytes(), format="audio/wav")
            if segment.get("overflow_ms", 0) > 0:
                st.warning(f"Exceeds window by {segment['overflow_ms']:.0f} ms. Review wording or generate another take.")
            if segment.get("error"):
                st.error(segment["error"])
    st.subheader("Generate audio")
    voice = st.text_input("ElevenLabs voice ID", value=manifest.get("voice_id", ""))
    model = st.text_input("ElevenLabs model ID", value=manifest.get("model_id", "eleven_v3"))
    speed = st.number_input("Maximum speed-up", min_value=1.0, max_value=1.25, value=1.10, step=0.01)
    mp3 = st.checkbox("Also export MP3")
    reviewed = st.checkbox("I reviewed the text and want to generate speech")
    if st.button("Generate / resume", disabled=not voice or not reviewed):
        try:
            bar = st.progress(0.0)
            result = render(job, voice, model, speed, mp3,
                            lambda n, total, status: bar.progress(n / total, text=f"Cue {n}/{total}: {status}"))
            st.rerun()
        except (PipelineError, OSError, ValueError) as error:
            st.error(str(error))
    if manifest.get("error"):
        st.error(manifest["error"])
    for kind, path in manifest.get("exports", {}).items():
        file = Path(path)
        if file.exists():
            if kind == "wav":
                st.audio(file.read_bytes(), format="audio/wav")
            st.download_button(f"Download {kind.upper()}", file.read_bytes(), file.name, key=kind)
    report = job / "timing_report.json"
    if report.exists():
        if HAS_PANDAS:
            st.dataframe(read_json(report), width="stretch")
        else:
            st.json(read_json(report))
        st.download_button("Download timing report", report.read_bytes(), "timing_report.json")

    # Character-Locked Video Lip-Sync Section
    st.divider()
    st.subheader("Character-Locked Video Lip-Sync (Hugging Face ZeroGPU)")
    st.caption("Synchronize lips with master audio while automatically detecting and preserving B-Roll, product cutaways, and mannequins.")

    v_col1, v_col2 = st.columns(2)
    video_upload = v_col1.file_uploader("Upload Source Video (.mp4, .mov)", type=["mp4", "mov"])
    ref_upload = v_col2.file_uploader("Optional: Reference photo of main speaker (for character-locking)", type=["jpg", "jpeg", "png"])

    dry_run_opt = st.checkbox("Dry run mode (Test B-roll detection and shot stitching locally without calling cloud GPU)", value=False)
    custom_space = st.text_input("Hugging Face Space (Leave default for LatentSync ZeroGPU)", value="fffiloni/LatentSync")

    master_audio = None
    if (job / "exports" / "fitted.wav").exists():
        master_audio = job / "exports" / "fitted.wav"
    elif (job / "combined_fitted.wav").exists():
        master_audio = job / "combined_fitted.wav"

    can_lipsync = video_upload is not None and master_audio is not None

    if not master_audio:
        st.info("Please generate speech above first to create the fitted master audio track.")

    if st.button("Run Smart Lip-Sync", disabled=not can_lipsync):
        try:
            with st.spinner("Analyzing camera shots, detecting B-roll, and synchronizing lips..."):
                source_video_path = job / "source_video.mp4"
                source_video_path.write_bytes(video_upload.getvalue())

                ref_img_path = None
                if ref_upload:
                    ref_img_path = job / "reference_speaker.jpg"
                    ref_img_path.write_bytes(ref_upload.getvalue())

                from src.video_dubbing import run_video_dubbing
                final_vid, vid_manifest = run_video_dubbing(
                    source_video_path=source_video_path,
                    master_audio_path=master_audio,
                    job_dir=job,
                    reference_image_path=ref_img_path,
                    dry_run=dry_run_opt,
                    space_name=custom_space
                )
                st.success(f"Video dubbing complete! ({vid_manifest['a_roll_count']} A-Roll shots synced, {vid_manifest['b_roll_count']} B-Roll shots preserved)")
                st.rerun()
        except (PipelineError, OSError, ValueError) as error:
            st.error(str(error))

    vid_manifest_path = job / "video_dubbing_manifest.json"
    if vid_manifest_path.exists():
        v_manifest = read_json(vid_manifest_path)
        final_video_file = Path(v_manifest.get("final_output", ""))
        if final_video_file.exists():
            st.video(str(final_video_file))
            st.download_button("Download Lip-Synced Video", final_video_file.read_bytes(), final_video_file.name)

        st.write(f"**Shot Analysis Breakdown:** {v_manifest['shots_count']} shots ({v_manifest['a_roll_count']} A-Roll, {v_manifest['b_roll_count']} B-Roll)")
        if HAS_PANDAS:
            st.dataframe(v_manifest["shots"], width="stretch")
        else:
            st.json(v_manifest["shots"])
