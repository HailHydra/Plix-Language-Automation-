Dual-model dubbing
=================

`dub` uses `lipsync-2-pro` for the selected visible speaker. All B-roll,
rejected people, and silent gaps keep their source visuals. `--broll-model`
remains accepted for old commands but is not used: moving a rejected
person's lips to the selected woman's narration is unsafe.

```powershell
.\.venv\Scripts\python.exe main.py dub --video "input\Dr. Priyanta - ACV - Hook - Sugar Damage Reel_English_FIXED_FINAL.mp4" --target en --target-frame 5.5 --sync-model lipsync-2-pro
```

The CLI requests confirmation before paid Sync generations. `--dry-run`
uses a separate subdirectory and never submits provider jobs.
When the chosen reference frame has multiple faces, use
`--target-point X Y` to select the intended woman's face. The pipeline
uses face embeddings to find her after cuts and passes explicit coordinates
to Sync. Missing or uncertain matches remain visually untouched.

The translated script is checked for repeated phrases. If it needs
correction, supply both `--reviewed-transcript` and `--reviewed-audio`.
They must match and cover the full video timeline. This also allows an
externally isolated speaker track to bypass whole-video dubbing.
The source dub can still contain two audible speakers; the face reference
does not separate voices. Review or isolate that audio before the final
export if both women speak. If the provider returns a video from its audio
endpoint, its audio is extracted to a separate MP3 automatically.

To use a previous voiceover, add `--broll-audio "path\previous_output.mp4"`.
This accepts an audio file or video's audio track aligned to the full source
timeline. Only B-roll uses this override. It does not synthesize or improve
the voice; presenter audio still comes from the cached dubbing master.
Lip-sync model choice does not select a TTS voice.

Sync output audio stays paired with its video. Each segment has an exact
frame budget; excess frames are trimmed and short video results fail
validation. Segments use PCM audio before final AAC encoding to avoid
accumulating encoder padding at joins.

New results are written to `final_dual_model_*.mp4`. Existing original
outputs and provider clips are retained. Cache keys include model, source,
audio, selected face, frame boundaries and dry-run status. Legacy results without these
keys are retained but not silently reused, so the first production run of
this workflow can incur new generation charges.

Validation: `python -m unittest discover -s tests -p test_video_dubbing_pipeline.py`
and `python -m unittest discover -s tests -p test_dub_assembly.py`.
