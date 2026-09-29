# SRT to Regional-Language Audio: Implementation Plan

## Implementation status — 2026-09-15

The first usable implementation is available in this directory:

- Separate `input/` and `output/` directories, with an included SRT and illustrative translation JSON.
- Python CLI: prepare, render/resume, and edit/selectively regenerate.
- Configurable LibreTranslate adapter, explicit source/target languages, optional detection, and reviewed-file translation input.
- ElevenLabs model/language/voice preflight, cached speech responses, saved alignment, and bounded transport retries.
- Measured PCM timing, conservative pitch-preserving speed adjustment, overflow review, streamed timeline assembly, WAV/MP3 export, and timing reports.
- Streamlit interface for upload, text review, cue edits, audio previews, generation, and downloads.
- Project-local `.venv` with dependencies installed; 27 automated tests pass, including the review UI flow. Dependency check passes.

Tests use synthetic audio and mocked provider responses. Real ElevenLabs generation, translation-provider quality, and native-speaker listening validation remain pending credentials and a selected voice/model.

This version preserves one source cue per speaking window. Context-aware automatic translation, automatic sentence grouping/retimed word subtitles, glossary enforcement, and translation-preparation resumption remain extensions. The LibreTranslate adapter exposes surrounding text for human review and rejects unsupported language pairs. See README.md for commands and exact limitations.

## Existing bilingual subtitles

Already-translated subtitles bypass LibreTranslate entirely. The importer supports source/translation lines within one SRT (explicit order and source-line count) or two SRT files with matching cue windows. English/source text is retained for review, and only target text is sent to ElevenLabs. Both preserve the original timing windows. The review UI defaults to bilingual input. Automated tests verify translation bypass and target-only speech generation.

## Objective

Generate natural regional-language speech using ElevenLabs and an SRT file. Keep translation language-agnostic: configure source and target languages per job, with no hard-coded language pair. Start with one narrator; Malayalam is an illustrative example only. Verify actual generated speech against every available speaking window before exporting audio synchronized to the original timeline.

## Initial scope and assumptions

- Input: UTF-8 SRT, source language (explicit or detected), target language, optional locale, voice ID, and a model supporting that target language.
- Translate only when the input text is not already in the target language.
- Default mode: preserve the original subtitle timeline for video synchronization.
- Optional later mode: natural narration with newly generated subtitle timings.
- Output: WAV, optional MP3, corresponding SRT, and a timing review report.
- Multiple speakers, voice cloning, video mixing, and a web interface are later extensions.

## Architecture

Use a Python command-line pipeline initially, with FFmpeg/ffprobe for audio processing and measurement. Keep parsing, translation, speech generation, timing verification, and assembly in separate modules.

SRT -> validation -> contextual translation -> segment planning -> ElevenLabs generation -> duration verification -> adjustment/review -> timeline assembly -> export

Store the ElevenLabs API key in a backend environment variable. Do not commit credentials or include them in logs.

## 1. Parse and validate subtitles

- Extract cue ID, start time, end time, and text.
- Reject invalid or non-positive time windows; flag overlaps and unordered cues.
- Normalize whitespace and remove formatting markup without losing spoken content.
- Preserve original text and timestamps for review and traceability.
- Detect non-speech captions and decide explicitly whether to skip them.

## 2. Prepare target-language text

- Use a language-agnostic translation interface accepting source language, target language, locale, glossary, and contextual text. Keep the translation provider separate from ElevenLabs speech generation.
- Detect the source language only when unspecified; flag uncertain or mixed-language input for review. Skip translation when source and target match unless locale adaptation is requested.
- Preserve Unicode and use the appropriate target-language script for speech generation. Configure language-specific normalization and pronunciation rules rather than embedding Malayalam-specific logic.
- Validate translation-provider and speech-model language support separately; report unsupported selections before generation. Language-agnostic architecture does not imply every provider supports every language.
- Example: breakfast may be rendered as “പ്രഭാതഭക്ഷണം”; confirm wording and pronunciation in context with a Malayalam speaker.
- Translate with neighboring sentences as context while preserving mappings to source cues.
- Maintain a glossary for names, numbers, abbreviations, and domain terms.
- Allow text review before paid generation.
- Select the ElevenLabs model after verifying its current target-language support and evaluate candidate voices with a short sample.

## 3. Plan speaking segments

Subtitle boundaries do not always match sentence boundaries. Group adjacent cues only when they form a natural phrase and their timing permits it. Retain the source cue IDs for every group.

For each segment store:

- Segment ID and source cue IDs.
- Original and target text.
- Start, end, and available duration in milliseconds.
- Source language, target language, locale, translation provider/settings, voice ID, model ID, and generation settings.
- Audio path, measured duration, adjustment history, and review status.

Do not silently consume the next cue's time. Borrowing an adjacent silent gap must be an explicit configurable policy. If grouping changes delivery across cue boundaries, regenerate subtitle alignment for the spoken text rather than claiming the original cue timing still matches it.

## 4. Generate and cache speech

- Send target-language text to ElevenLabs in natural phrase or sentence segments.
- Keep voice and settings consistent across the file.
- Save each original response before processing it.
- Cache by text, language, model, voice, and generation settings so unchanged segments can be reused.
- Use bounded retries with backoff for transient failures and rate limits.
- Save progress so interrupted jobs can resume; limit concurrency according to the account's current limits.
- Where supported, request speech alignment to help inspect speech boundaries and produce output subtitles.

The speech-with-timestamps API returns alignment for generated speech. It does not by itself force audio into the supplied SRT window.

## 5. Verify the audio window

Never estimate final fit from character count, word count, or English pronunciation. Measure actual generated target-language audio in its full phrase context.

For each segment:

available_ms = end_ms - start_ms
fit_ratio = processed_clip_duration_ms / available_ms

Measure decoded audio duration. Inspect speech boundaries using alignment or voice activity detection when available. Distinguish leading/trailing silence from internal pauses, and preserve natural word boundaries and breathing. Use the final processed clip length when checking placement on the timeline.

Illustrative example only: a cue from 5.0 to 6.5 seconds offers 1.5 seconds. A measured 1.2-second clip fits. A 1.6-second clip may need a small adjustment. A 2.2-second clip needs wording or timing review. These are not measured durations for the Malayalam example.

### Fit policy

1. If the clip fits, place it at the segment start and leave the remaining gap as silence.
2. If it slightly exceeds the window, remove only verified excess edge silence, then consider a modest pitch-preserving speed adjustment.
3. Re-measure after every change and check intelligibility.
4. If it substantially exceeds the window, review a shorter equivalent translation or regenerate with supported pacing controls.
5. Meaning-changing rewrites require review; do not silently omit content to make it fit.
6. After a bounded number of attempts, mark the segment for review rather than truncating speech or shifting later cues.

A provisional maximum speed-up of 1.10x can be evaluated during the pilot. This is a configurable starting point, not a guarantee of natural speech. Use native-speaker listening to establish acceptable limits.

Store statuses such as pending, generated, fits, adjusted, needs_review, and failed. Include available duration, measured duration, overflow, applied speed, and attempt count in the report.

## 6. Assemble and export

- Convert segments to a common PCM sample rate and channel layout.
- Place each clip at its absolute timeline start, avoiding cumulative timing drift.
- Preserve gaps as silence and check all final clip boundaries for overlap.
- Export WAV first; optionally encode MP3 and verify its decoded timing because compression can introduce padding.
- Preserve original cue timings only where they still correspond to the delivered speech. Otherwise export newly aligned subtitles and keep the original SRT separately.
- If video is supplied later, use its duration for the final track length; otherwise default to the last subtitle end.
- Block an automatic final-ready result when unresolved overlaps, missing speech, or failed segments remain. Permit a clearly labeled preview for review.

## 7. Quality checks

Timing and language quality are separate acceptance criteria:

- Every segment is present and completes within its permitted window.
- No spoken word is clipped and no unintended speech overlap occurs.
- Target-language pronunciation, meaning, names, and numbers are correct.
- Pace, pauses, and voice remain natural across segment boundaries.
- Final audio and exported subtitles correspond to each other.

Automated transcription can assist with spotting missing or altered words, but it is not proof of correct pronunciation. Include target-language native-speaker review of the pilot and any heavily adjusted segments.

## Suggested project structure

src/
  srt_parser.py
  translation.py
  segment_planner.py
  elevenlabs_client.py
  timing.py
  assembly.py
  pipeline.py
runs/<job_id>/
  manifest.json
  source.srt
  segments/
  timing_report.json
  output.wav
  output.mp3
  output.srt

## Implementation phases

### Phase 1: Short pilot

Use a 30–60 second sample with short and long phrases in a selected target language. Validate a second supported language pair before considering the language-agnostic translation interface complete. Parse the SRT, generate one voice, measure segment durations, and produce a timing report. Confirm pronunciation and model suitability before processing larger files.

### Phase 2: Timing and export

Implement silence placement, conservative duration adjustment, bounded regeneration, unresolved-segment review, timeline assembly, and subtitle export.

### Phase 3: Reliability

Add caching, resumable jobs, retry limits, usage tracking, and targeted checks for malformed SRT, overlaps, Unicode text, long utterances, and timing drift.

### Phase 4: Review interface

Add upload, language and voice selection, text editing, segment previews, timing flags, selective regeneration, and downloads.

## Decisions to confirm before implementation

- Source SRT language and whether translation is needed.
- Target language, regional dialect or locale, tone, and voice.
- Whether timestamps are strict and whether adjacent silent gaps can be used.
- Expected file lengths and processing volume.
- Whether original audio/video will also be available.

## References

Verify model support and API options again during implementation:

- ElevenLabs models: https://elevenlabs.io/docs/overview/models
- Text to speech: https://elevenlabs.io/docs/overview/capabilities/text-to-speech
- Speech with timestamps: https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps

