# Operator Recipes

Resolve `command -v voices` and doctor first. All examples use the installed
canonical CLI; another project's `uv` environment is not an integration path.

## Optional DGX compute

Omission selects MLX. Use DGX only when explicitly selected for this invocation
or studio session and its operator has admitted a vacant lane. Existing SSH
authorization with strict known hosts and the retained offline CUDA image, two
audio overlays and pinned checkpoints are prerequisites, not work this skill
provisions. Never stop another workload, download a replacement foundation,
install the Mac MLX wheel remotely or fall back automatically.

```bash
voices --compute dgx --dgx-host <existing-alias> --dgx-ssh-config <existing-config> \
  --json doctor
voices --compute dgx --dgx-host <existing-alias> --dgx-ssh-config <existing-config> \
  ui --no-open
```

`--dgx-ssh-config` is optional when the existing SSH configuration suffices.
Keep these global compute options before any operation's subcommand. The same
selection covers VoiceDesign, Base TTS, audio-only ASR and supplied-text
alignment. Library, capture, normalization, review, playback and exact-preview
export remain on Mac; audio/text inputs for inference go to the selected DGX.
Use selected `compute.models` revisions from doctor, never the MLX SHAs in the
examples below. Doctor's local `runtime` proves neither remote readiness nor
CUDA identity. A real inference still needs the requested operation's intent.
Unknown transport/cancellation outcomes require
[same-invocation recovery](state-and-recovery.md#interrupted-dgx-work), not retry.

## Direct local playback

When the user wants to hear something now:

1. verify readiness with `voices --json doctor`
2. inspect the saved library with `voices --json list`
3. resolve a likely candidate with `voices --json resolve <id-or-name>` when the choice is not exact
4. choose a suitable existing voice; if none fits and creation was not requested, offer the closest available voice or explain the need to create one before proceeding
5. use `voices say ... --voice <voice_id>` for immediate playback
6. use `voices --json render <voice_id> --text-file <path>` when a file artifact also matters

## Persisted render and supplied-text alignment

With explicit model-inference intent:

```bash
voices --json render <voice_id> --text-file <text-path> \
  --model-revision a6eb4f68e4b056f1215157bb696209bc82a6db48
voices --json align --audio <audio-path> --text-file <text-path> \
  --language English \
  --model-revision 53c8c0e46733eec430e4b53dd6471d0e5dee45f8
```

These example revisions are for MLX; the standard shared cache resolves
immutable snapshots, never `refs/main`. DGX uses its selected retained revisions.
Render's new sidecar records its revision and observed runtime; inspect it via
`outputs show`. Alignment returns exact supplied text, original audio hash,
normalized waveform identity and `words` with `text/start/end` in seconds.
`spoken_content_verified` is false: supplied words are positioned, not
independently recognized. Times are estimator-adjusted; zero-width words are
allowed. `timing_diagnostics` is null because raw corrections are unavailable.
Do not use alignment instead of audio-only ASR or listening to assess omissions.
Neither capture nor playback is started by alignment. On MLX, Japanese requires
`nagisa` and Korean requires `soynlp`; a missing dependency fails before loading
the model. DGX keeps tokenizer dependencies in its remote runtime. Report a
missing dependency rather than silently installing packages or switching engines.

## Audio-only recognition

For a separate transcript from an existing WAV, with explicit inference intent:

```bash
voices --json transcribe --audio <wav-path> --language Italian \
  --model-revision e1f6c266914abc5a46e8756e02580f834a6cf8a7
```

Use a public language name (`English`, `Italian`, or another `languages` label),
not a language code. On MLX, doctor's `models.stt` and `model_revisions.stt`
identify the configured ASR; DGX uses `compute.models.asr`, not that MLX revision.
This command takes no supplied text and makes no clone candidate,
voice, review file, capture or playback. Retain `transcript` with its original
and normalized `audio` hashes, `model_id`, `model_revision` and `runtime` when
comparing to the intended words. Recognition differences are evidence to
review, not an automatic pronunciation or listening-quality verdict.

## Interactive record flow in an agent harness

When the agent is about to run `voices record` interactively:

1. ask the operator to choose the language first
2. run `voices --json record plan --mode guided --language <language>` or the free-mode equivalent
3. show the exact guided script for that language
4. state the actual record window or stop rule before starting capture
5. only then launch the recording command
6. after capture, make take playback explicit before transcript approval
7. never force the operator into blind transcript edits

## Clone from an imported file

When the operator already has an audio file:

1. use `voices --json clone review --audio <path> --language <language> --review-out <review.json>`
2. if no transcript exists yet, let the selected backend's STT draft it
3. inspect the review JSON and play the normalized review WAV when needed
4. save only after the operator approves audio and transcript with `voices --json clone save --review <review.json> --id <id> --name <name>`
