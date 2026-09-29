# Text to Audio

Language-agnostic SRT translation and ElevenLabs narration with measured timing checks.

## Directories

- input/: source SRT files and optional reviewed translations.
- output/<job-id>/: source snapshot, editable manifest, per-cue audio, timing report, and versioned exports.
- output/.cache/speech/: reusable ElevenLabs responses and character alignment.
- src/: pipeline modules.
- app.py: local review interface.
- main.py: command-line interface.

Input files remain separate from generated artifacts. The supplied Malayalam JSON is illustrative and should be reviewed by a fluent speaker.

## Setup (PowerShell, from this directory)

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\Activate.ps1
~~~

If PowerShell blocks activation, use .\.venv\Scripts\python.exe instead of python in the commands below.

Edit .env locally to set ELEVENLABS_API_KEY. Set LIBRETRANSLATE_URL and its optional API key only if using automated translation/detection. Do not paste secrets into source files or commit .env.

FFmpeg is resolved from FFMPEG_BINARY, PATH, or the imageio-ffmpeg package. The CLI uses Python's standard library plus the FFmpeg executable; Streamlit is only for the UI.

## Use subtitles that already contain translations

No LibreTranslate account, URL or API key is needed. Leave those settings blank and set ELEVENLABS_API_KEY for speech generation.

### One bilingual SRT

Example (English/source first, translated text underneath):

~~~srt
1
00:00:01,000 --> 00:00:04,000
Breakfast is ready.
???????????? ?????????.
~~~

In the UI select **Bilingual SRT**, **Source first**, and **1 source line per subtitle**. Set source code en and the actual target code, such as ml. English is retained for review; only the translated lines are synthesized.

~~~powershell
python main.py prepare input\bilingual.example.srt --source en --target ml --bilingual
~~~

Use --source-lines 2 when the source occupies two lines in every cue. Use --target-first when translated text appears before the source. This is explicit layout selection, not language guessing; it works for language pairs using the same alphabet. If line wrapping varies between cues, normalize the language boundaries or use separate aligned files. Review imported target text before generation.

### Labeled bilingual SRT

For entries containing [English]: and [Marathi]:, use explicit labels so only Marathi text is spoken and the labels themselves are removed:

~~~powershell
python main.py prepare input/priyanta_marathi_yeast_protein/bilingual.srt --source en --target mr --bilingual --source-label English --target-label Marathi
~~~

In the UI select **Bilingual SRT**, enable **Text has language labels**, enter the exact source/target labels, and set the target language code to **mr**. This validates both language sections, permits either order and wrapped lines, and rejects missing, duplicate or unexpected language labels.

### Two separate SRT files

Select **Separate source and translated SRTs** in the UI and upload both, or run:

~~~powershell
python main.py prepare input\english.srt --source en --target ml --translated-srt input\malayalam.srt
~~~

The files must have equal cue counts and identical start/end timestamps. Cue IDs may differ; alignment uses chronological position and verified timing. Mismatches are rejected before any speech calls.

For a file containing only translated text, choose **Target-language SRT only**. All of its text is spoken in the selected target language.


## Prepare and review

Already in the desired language:

~~~powershell
python main.py prepare input\example.srt --source en --target en
~~~

Use reviewed translations from any translation provider:

~~~powershell
python main.py prepare input\example.srt --source en --target ml --translations input\translations.example.json
~~~

Translation JSON is an object mapping every original cue ID to a nonempty target-language string. There must be no missing or extra IDs. This route supports any language pair for which you can supply text; speech support is checked independently.

Automatic translation through a configured LibreTranslate server:

~~~powershell
python main.py prepare input\example.srt --source en --target es --provider libre
~~~

Use --source auto for detection. The adapter checks each cue and rejects low-confidence or mixed-language results. Short cues may require an explicit source language. The server's /languages endpoint must advertise the selected pair; do not assume Malayalam is supported by every LibreTranslate installation.

Preparation makes no ElevenLabs generation calls. It prints the job directory. Review target_text in its manifest.json, or use the UI. Only edit target_text, skip, and revision; changed cue IDs or timing require a new preparation.

## Generate or resume

Replace JOB_ID, YOUR_VOICE_ID and YOUR_MODEL_ID with real values:

~~~powershell
python main.py render output\JOB_ID --voice YOUR_VOICE_ID --model YOUR_MODEL_ID --mp3
~~~

The model and voice are validated against ElevenLabs before synthesis. The target language must be advertised by that model. Regional language tags are not silently downgraded; use a supported base language code with an appropriate voice when necessary.

Each clip is decoded into mono 24 kHz PCM and measured. Speech shorter than its window leaves silence. Small overflows can use pitch-preserving speed-up (default cap 1.10x). Every adjusted result is measured again. Larger or remaining overflows are marked needs_review. The app never cuts off speech or moves the next cue to hide an overflow.

Inspect timing_report.json and cue previews. No new full-track export is made while any cue is unresolved. All successful exports are marked ready_for_listening_review: timing success does not prove pronunciation or meaning.

~~~powershell
python main.py edit output\JOB_ID --id 1 --text "Reviewed shorter equivalent text"
python main.py edit output\JOB_ID --id 2 --regenerate
python main.py render output\JOB_ID --voice YOUR_VOICE_ID --model YOUR_MODEL_ID
~~~

Use --skip yes to omit an explicitly reviewed non-speech caption. A fresh-take request increments revision and may incur another speech charge; unchanged segments use cache. Retrying generation is bounded at the transport layer; 429/transient HTTP failures have up to three attempts. Connection timeouts are not blindly retried because a request may already have been processed. Usage counters count successful uncached generations, not authoritative billing; provider retries may incur additional usage.

Rerenders clear current export references and use new export directories. Historical files remain available, but manifest.exports is the authoritative current output. A per-job lock prevents concurrent editing/rendering. After a crash, remove a stale .lock only after checking that the owning process has stopped.

## Local review UI

~~~powershell
python -m streamlit run app.py --server.address 127.0.0.1
~~~

Upload subtitles, choose source/target codes, prepare translations, edit cues, preview audio, selectively request new takes, and download the current exports/report. Credentials stay in the local environment. Save cue edits before rendering.

## Checks

~~~powershell
python -m unittest discover -s tests -v
~~~

Tests use synthetic tones and mocked provider responses: they verify processing and API contracts, not the quality of live speech. Live validation requires a configured account, a voice/model, and a native-speaker review of a short sample in at least two target languages.

## Current boundaries

- One narrator and one SRT cue per speaking window; overlapping source cues are rejected.
- The translation adapter interface accepts context, locale and glossary. LibreTranslate does not supply contextual/glossary controls in this adapter: surrounding text is shown for human review; locale/glossary enforcement requires reviewed translations or a future adapter.
- No automatic meaning-changing shortening or automatic trimming of quiet speech. Oversized clips go to review.
- Original subtitle windows are preserved at cue level. Saved character alignment is available for inspection; word-level retimed subtitles and cross-cue sentence grouping are future extensions.
- Job resumption and caching cover speech generation. A failed preparation must be rerun; completed partial translations remain in the failed manifest for recovery.
- No video mixing, background music, multiple speakers, or automatic transcription quality scoring.
- Audio generation cannot run until credentials and a supported model/voice are configured.

## API references

- https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps
- https://elevenlabs.io/docs/api-reference/models/list
- https://docs.libretranslate.com/api/operations/translate/
- https://docs.libretranslate.com/api/operations/languages/
