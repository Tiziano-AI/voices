# Local product contract

Current operating authority:

- installed CLI: resolve `command -v voices`; do not assume an installation directory
- runtime evidence: `voices --json doctor`, including executable, source identity, selected dependency versions, cache and default model revisions
- explanatory source contracts: `README.md` and `ARCH.md` in the [Voices repository](https://github.com/Tiziano-AI/voices); the bundled references cover operating the installed product without a checkout
- external consumers use this one installed CLI and standard shared Hugging Face cache, never their own Voices source/Python/venv, duplicate cache or provisioner

Repository development commands are not an operating fallback. Report missing or mismatched installation; do not create a private replacement.

## Product shape

`voices` is a local-first Apple Silicon voice studio built on Qwen3-TTS through MLX.

- Canonical public surface: CLI
- Supporting edge: bundled FastAPI browser UI
- Default voice library: `~/.voices`
- Default output directory: `./outputs`

Saved voices are reference assets, not trained models.

## Canonical commands

- global `--json`: machine-readable CLI mode; JSON goes to stdout and product-domain errors use the `error.code`, `error.message`, and `error.exit_code` envelope
- `doctor`: inspect local readiness, library source precedence, output root, studio bundle, FFmpeg, platform/runtime, configured model IDs/revisions and observed runtime identity without loading models
- `languages`: list supported language labels
- `list`, `resolve`, `show`: inspect, filter, resolve, and read saved voices
- `outputs list`, `outputs show`: inspect persisted render sidecars and WAV paths
- `design`: create one reference voice from a VoiceDesign description
- `design-batch`: create multiple design voices from `.jsonl` or `.txt` prompt files
- `clone review`: create a durable review handoff from imported audio and transcript or STT draft
- `clone save`: persist an operator-approved clone review as a saved voice
- `record plan`: inspect recording script, timing, and stop rule without using the microphone
- `record`: capture microphone audio and finish as a saved clone voice
- `say`: ephemeral playback through macOS speakers
- `render`: write a WAV plus JSON sidecar; `--model-revision` accepts a full 40-hex Base SHA
- `align`: estimate supplied-text word times from existing audio, with model revision/runtime and explicit non-verification semantics
- `transcribe`: recognize an existing WAV with required public language and immutable ASR revision; return transcript and audio/model/runtime identity without capture, playback or library writes
- `ui`: serve the bundled local browser UI
- `delete`: remove a saved voice; use `--dry-run` before destructive deletion

## Direct delivery contract

For direct spoken-output tasks:

- start with `doctor` to verify local readiness without loading models
- inspect the existing library with `list` and choose a suitable saved voice with `resolve`
- use `say` for ephemeral local playback or fast audition
- if the library is empty or no voice is suitable, explain that creation is needed or offer the closest available voice; a speech-only request does not itself cover saving a new library voice
- use `render` for persisted output with provenance or when you need a file artifact to hand back

For voice-creation tasks, including requests for a new persona or recurring narrator:

- use `design` when the target is persona-driven or synthetic
- use `clone review` then `clone save` when a real audio file already exists
- use `record` when the operator wants the product to capture the reference clip directly
- treat `record` as an ingress into clone save, not as a separate persisted voice type
- use `record plan` before interactive capture when an agent harness is driving the flow

## Current language contract

Product-supported languages:

- `Chinese`
- `English`
- `French`
- `German`
- `Italian`
- `Japanese`
- `Korean`
- `Portuguese`
- `Russian`
- `Spanish`

`Auto` exists upstream but is not a supported product input in this repo.

## Local runtime boundary

The local adapter currently exposes two relevant generation paths:

- Voice design through `generate_voice_design(text, instruct, language)`
- Reuse through Base-model `generate(text, ref_audio, ref_text, lang_code)`

The local product does not expose the full upstream `qwen_tts` helper surface directly.

The same MLX STT adapter assists record/clone review and public audio-only `transcribe`; no private runtime is needed.

## Persisted voice layout

Each saved voice lives under:

```text
~/.voices/<voice_id>/
  reference.wav
  reference.txt
  voice.json
```

Runtime reads and writes schema v2 only.

Rendered outputs live under:

```text
./outputs/<voice_id>/
  <timestamp>__<text-slug>.wav
  <timestamp>__<text-slug>.json
```

Output sidecars remain schema v2. New renders add `base_model_revision` and `runtime`; old sidecars without these fields remain unchanged and read as unknown/null. Runtime source SHA-256 covers installed Python bytes at observation, not a Git commit or previously imported bytecode; package versions cover the declared selected-dependency scope. Do not manufacture historical provenance or promise byte-identical regeneration. Use `outputs list` and `outputs show`, not filenames or Rich tables.

## Prompt-pack contract

`design-batch` accepts:

- `.jsonl` rows with `id`, `instruct`, and optional `name`, `language`, `text`
- `.txt` prompt lines, with shared seed text supplied separately

If a `.jsonl` row omits `text`, the operator must still provide shared seed text through `--text` before the pack is runnable.

The repository's `examples/prompts` contains optional seeds, not an installed prerequisite or canonical policy. Author a pack with the bundled prompt workbench when no checkout is available.

## UI contract

The bundled UI supports:

- browse and filter
- preview playback of saved references
- same-line compare across multiple saved voices
- exact-preview export or a new render, both with WAV and provenance sidecar
- a creation hub with `Design`, `Clone file`, and `Record live`
- explicit review-time playback for imported and recorded take review before save
- transcript review before saving imported or recorded clone voices
- immediate detail clearing when the selected voice changes so stale metadata is not shown for a new target

The UI is a supporting local edge. The CLI remains canonical.

The UI lifecycle contract is:

- `voices ui` launches one local FastAPI/browser process for the selected library and port
- `--host` accepts loopback hosts only: `127.0.0.1`, `localhost`, or `::1`
- `--port` selects the listening port for that process
- cleanup uses the terminal process that launched `voices ui`; there are no `voices ui status` or `voices ui stop` subcommands
