# Voices

`voices` is an Apple Silicon voice studio using Qwen3-TTS through MLX. Keep
reference voices under `~/.voices`, audition and compare lines, and export
speech from the CLI or bundled browser studio.

Use `design` for a synthetic voice, `clone` to import a recording, or `record`
for microphone capture. The CLI is the automation contract; `voices ui` guides
the same workflows in a browser.

## Requirements

- Apple Silicon Mac
- Python `>=3.14.7,<3.15` (`.python-version` selects `3.14.7`)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [pnpm](https://pnpm.io/installation) and Node.js for source builds; `web/package.json` selects their versions
- FFmpeg on `PATH` for audio import/review, recording, `transcribe` and `align`

## Setup

```bash
git clone https://github.com/Tiziano-AI/voices.git
cd voices
pnpm --dir web install --frozen-lockfile
pnpm --dir web build
uv sync --locked
```

Run pnpm with `--dir web` to select the package's build toolchain. The Python
and pnpm locks own dependency resolution; ambient tools are not replaced.

Build the web bundle **before** Python sync: Hatch includes it during setup.
A prebuilt wheel includes the UI and needs neither Node nor pnpm. See
[installation and removal](devtools/README.md#repository-and-global-command).

Models resolve full immutable revisions in the shared standard Hugging Face cache: VoiceDesign for `design`, Base for `say`/`render`, ASR for transcript review and `transcribe`, and ForcedAligner for `align`. Missing snapshots may download on first authorized use; runtime never selects mutable `refs/main`.

After the UI build, `uv build` packages wheel and sdist. Wheels use
`voices/web_dist`; editable checkouts use `web/dist`. Launch never builds.

`uv run voices` uses this checkout; `uv sync` never updates a global CLI.

## First saved result

Run `uv run voices --json doctor`, then `uv run voices ui`. Choose **Design**, create a synthetic voice, audition a line, then **Save preview** to keep that exact WAV and its JSON sidecar. CLI `render` generates a new performance:

```bash
uv run voices design --id studio_narrator --name "Studio Narrator" --language English \
  --instruct "A calm adult narrator, clear diction, natural pacing, no theatrical emphasis." \
  --text "A small idea becomes useful when someone can put it to work." --dry-run
# These next commands generate audio and may download the pinned model snapshots.
uv run voices design --id studio_narrator --name "Studio Narrator" --language English \
  --instruct "A calm adult narrator, clear diction, natural pacing, no theatrical emphasis." \
  --text "A small idea becomes useful when someone can put it to work."
uv run voices --json render studio_narrator "This is a line worth keeping."
uv run voices --json outputs list --voice studio_narrator
```

Use only recordings you have permission to use for cloning. Nothing captures a microphone or starts model inference on install. Stop the studio with Ctrl-C in its terminal. Removing the CLI or its agent guidance does not remove your library, renders, model cache or saved review files; those are separate user assets.

## Codex App local actions

`.codex/environments/environment.toml` supplies optional top-bar actions:
`Setup`, `Run Studio`, `Doctor`, `Build UI`, `Gate`, `Python Tests`, `Web Checks`
and `List Voices`. Setup follows the build-before-sync order above. These are
conveniences over the CLI, not a separate API. Parameterized, destructive,
audio-device and model-heavy operations remain explicit CLI commands.

## Agent plugin

The [Voices plugin](PLUGIN.md) packages `skills/voices-local-studio` for Agent
Plugins and Claude Code. Install CLI/models independently; the plugin runs no
setup, hook, downloader or MCP server. Removal preserves CLI, cache and audio.

## Canonical command surface

### `ui`

Launch the bundled local browser studio.

```bash
uv run voices ui
uv run voices ui --library ~/.voices --port 9901 --no-open
```

The studio shares CLI workflows and storage, binds only to loopback, validates
Host on every route and rejects cross-origin mutations against the actual
listener port. Forwarded headers are not trusted. `::1` uses a bracketed IPv6 URL. Missing
bundle assets produce a setup error; launch never builds them.

### JSON mode

Add global `--json` before the command when Codex or another tool needs stable output:

```bash
uv run voices --json doctor
uv run voices --json list --language English --source design --query noir --limit 20
uv run voices --json resolve noir
uv run voices --json show noir_narrator
uv run voices --json outputs list --voice noir_narrator --limit 20
uv run voices --json outputs show noir_narrator 20260408T120000Z__line.wav
```

- JSON success payloads write one JSON document to stdout
- human progress and diagnostics stay off stdout in JSON mode
- collection payloads use `items`, `count`, and `limit`
- product-domain failures use `{"error":{"code":"...","message":"...","exit_code":2}}`

### `doctor`

Inspect readiness without loading models.

```bash
uv run voices doctor
uv run voices --json doctor
```

- reports the effective voice library path and validated voice count
- reports the output root, bundled studio bundle, and FFmpeg availability
- reports `auth_required: false`, runtime identity (executable, source SHA-256 and selected dependency versions), configured model IDs/revisions, and library precedence
- exits with the library-integrity error if the saved voice library contains invalid entries

### `languages`

Inspect the product-supported language labels.

```bash
uv run voices languages
uv run voices --json languages
```

### `design`

Create one reference voice from a VoiceDesign description.

```bash
uv run voices design \
  --id noir_narrator \
  --instruct "Low, smoky, restrained authority, measured pacing." \
  --text "Control is not the absence of feeling. It is the discipline to place it exactly where it belongs." \
  --language English \
  --name "Noir Narrator"
```

- `--id` must be a strict slug such as `noir_narrator` or `matteo-01`
- `--overwrite` replaces an existing saved voice at the same id
- `--instruct` is the VoiceDesign description for the target voice
- `--dry-run` validates and reports the voice that would be created without loading the model or writing the library

### `design-batch`

Create multiple design voices from a prompt pack.

```bash
uv run voices design-batch examples/prompts/basic.jsonl \
  --text "Control is not the absence of feeling. It is the discipline to place it exactly where it belongs." \
  --language English
```

- Supported prompt files: `.jsonl` and `.txt`
- `.txt` prompt files require `--text` to supply the shared seed text
- Comment lines starting with `#` are ignored in `.txt` prompt files
- `--dry-run` previews the voices that would be created without generating them
- `--overwrite` replaces existing saved voices with matching ids

### `clone review` and `clone save`

Import a reference voice from audio plus transcript in two explicit phases.

```bash
uv run voices --json clone review \
  --audio ~/Downloads/recording.opus \
  --transcript "Esatta trascrizione dell'audio." \
  --language Italian \
  --review-out ./matteo-review.json

uv run voices --json clone save \
  --review ./matteo-review.json \
  --id matteo \
  --name "Matteo"
```

- `ffmpeg` must be available on `PATH`
- `clone review` routes imported audio through the same transcript-review owner used by `record` and the browser studio
- `--transcript` seeds the review draft when you already have a correct transcript; when omitted, local STT creates the draft
- the review file stores the approved transcript draft plus a normalized WAV sibling so `clone save` has one explicit persistence input
- `clone save --overwrite` replaces an existing saved voice at the same id

### `record`

Record a reference voice from your microphone and save it as a clone voice.

```bash
uv run voices record --language English
uv run voices record --mode free --language Italian
uv run voices record --mode guided --script "Your custom line here." --language English
uv run voices --json record plan --mode guided --language English
```

- `record` is the easiest ingress into the clone workflow; when it succeeds, the voice is already in your library
- `guided` mode uses a curated per-language script and auto-stops after `30s`
- `free` mode records until you stop it and enforces a minimum usable duration
- both modes let you listen to the captured take, run STT, and show the actual transcript so you can `accept`, `retry`, `edit`, or `play` before save
- in the browser, a failed transcript review keeps the captured take for **Retry review** or **Download take**, without reopening the microphone; Reset or closing the recording panel discards that unsaved browser take
- closing or resetting while microphone permission is pending retires any late-granted stream without starting a recording; already-active tracks are stopped on close
- `--name` must be non-empty after trimming; when `--id` is omitted and `--overwrite` is set, `record` overwrites the slug derived from the approved name instead of creating a suffixed new id
- `ffmpeg` must be available on `PATH`
- `record plan` reports the guided script, target duration, free-mode minimum, and stop rule without using the microphone

### `say`

Speak immediately through macOS speakers.

```bash
uv run voices say "We proceed at dawn." --voice noir_narrator
```

- `--voice` is optional; when omitted, `say` uses the most recently created saved voice
- when the library is empty, `say` points you at `design`, `clone`, or `record` as the canonical first-success creation paths
- text must be non-empty after trimming
- `say` is ephemeral playback and does not create persisted render artifacts

### `render`

Render a WAV plus JSON sidecar.

```bash
uv run voices render noir_narrator "We proceed at dawn."
uv run voices render noir_narrator --text-file ./line.txt --play
```

- `--text-file` reads render text from a file instead of a positional argument
- `--out-dir` chooses the output root; the default is `./outputs`
- concurrent renders serialize basename reservation per voice so collisions become `-2`, `-3`, and so on instead of clobbering a sibling export
- the output root and per-voice directories must be real paths; served artifacts stay under that configured root, and symlinked output paths are rejected
- `--play` plays the rendered WAV after saving it
- `--model-revision` selects a full 40-hex Base revision; the default is `a6eb4f68e4b056f1215157bb696209bc82a6db48`
- new schema-v2 sidecars retain `base_model_revision` and generation-time `runtime` identity; older sidecars remain unchanged, with missing identity unknown rather than reconstructed

### `transcribe` and `align`

`transcribe --audio WAV --language English --model-revision SHA` recognizes
words without a supplied transcript. All options are required; use public
language names such as `English` or `Italian`. `align --audio PATH --text-file
PATH --language English [--model-revision SHA]` estimates supplied-word times
and explicitly does not verify spoken content.

Both return audio/model/runtime identity under global `--json`, use local
inference and may download a pinned model. Neither captures, plays or saves
audio, voices or review files. See [existing-audio inference](docs/audio-inference.md)
for copyable pinned examples, JSON fields, language dependencies and claim limits.

### `list`, `resolve`, `show`, `outputs`, and `delete`

Inspect the library, resolve human input to stable ids, inspect rendered outputs, and manage saved voices.

```bash
uv run voices list
uv run voices list --language English --source design --query noir --limit 20
uv run voices resolve noir
uv run voices show noir_narrator
uv run voices outputs list --voice noir_narrator
uv run voices outputs show noir_narrator 20260408T120000Z__line.json
uv run voices delete noir_narrator --yes
uv run voices delete noir_narrator --dry-run
```

- `list` shows `id`, `lang`, `source`, and wrapped `desc`
- `list` filters by `--language`, `--source`, `--query`, and `--limit`
- when the library is empty, `list` points you at `design`, `clone review`, `clone save`, and `record` as the canonical first-success creation paths
- `resolve` returns one exact or unambiguous saved `voice_id`
- `show` prints the full persisted metadata plus derived `description` and `source_kind`
- `outputs list` reads persisted render sidecars under `./outputs/<voice_id>/`
- `outputs show` accepts either a WAV or JSON sidecar filename and returns the persisted output metadata plus artifact paths
- `delete --dry-run` reports the voice that would be deleted without removing files
- `delete --yes` removes a saved voice without an interactive confirmation step

## Bundled browser studio

The empty-library launchpad guides voice creation; the studio supports audition,
comparison, design, clone/record review and export.

The workbench combines a voice rail, preview controls, Audition Board,
transport/inspector and creation sheet. Palettes change appearance, not behavior.

Browser integrity and playback:

- actual saved-library corruption shows the dedicated library integrity blocker
- other bootstrap or local-edge failures show a retryable studio blocker instead of pretending the library itself is broken
- closing the creation sheet, switching creation paths, or retrying a clone or record review abandons the in-flight browser request instead of letting a late response mutate the current studio state
- design and batch design check cancellation before each save; closing after that cutoff does not undo persistence, and earlier batch saves remain
- changing the selected voice clears stale detail immediately until the fresh detail payload arrives
- saved-reference audition failures surface as visible studio errors
- browser playback is owned by one audio session; `playing` is shown only after the browser accepts playback, and browser denial is shown as blocked/error state
- cards retain each performance; freshness follows exact inputs and the latest observed library, not names or ordering
- generation covers unattempted voices; failed cards have explicit retry, and old clips/links survive input changes

Aborting a request does not prove its save was canceled: inspect saved state before retrying. **Save preview**, **Save clip**, **Save original clip** and **Save compared clips** keep exact auditioned bytes/provenance and reuse one output pair. Expired tokens fail without resynthesis. CLI `render` and **Render export** without a preview create new audio. [Performance identity](docs/performance-identity.md) explains freshness, original-clip saves and input conflicts.

Storage stays shared with the CLI:

- saved voices still live only under `~/.voices`
- previews, compare clips, and Audition Board positions are session-only browser state
- saved exports still write WAV plus schema v2 JSON into `./outputs`
- prompt-pack and audio uploads are bounded by the local upload limit
- oversized browser multipart uploads are rejected before form parsing when the request declares a too-large `Content-Length`

## Saved assets

Library precedence is `--library` > `VOICES_LIBRARY` > `~/.voices`. Each voice
directory holds `reference.wav`, `reference.txt` and schema-v2 `voice.json`.
Saved voices are reference assets, not trained models. Overwrite stages the
replacement before swapping it in; missing, mismatched or symlinked assets
fail integrity checks.

Renders write `outputs/<voice_id>/<timestamp>__<slug>.{wav,json}` by default.
Collisions append `-2`, `-3`, and so on to both files. The sidecar names its
matching WAV basename; writes and downloads reject symlinked or non-directory
output owners. Previews and comparisons remain temporary, not saved renders.

## Language handling

Supported languages: `Chinese`, `English`, `French`, `German`, `Italian`, `Japanese`, `Korean`, `Portuguese`, `Russian`, `Spanish`.

Use `--language` explicitly whenever the target spoken language is not the default `English`.

For `voices design`, `--instruct` is the VoiceDesign description. Official hosted Voice Design guidance recommends English or Chinese descriptions. The local MLX/Qwen runtime does not enforce that restriction, so `voices` treats it as guidance, not as a validation rule.

`Auto` remains an upstream Qwen capability, but it is not a supported product input in this repo.

The local STT runtime can support a broader set of languages, but the product intentionally constrains `design`, `clone`, and `record` to the same 10 supported languages so the saved library and synthesis surface stay aligned.

## Prompt packs

`examples/prompts/basic.jsonl` is a neutral two-voice starter pack. Preview its
output paths with `design-batch --dry-run` before generating audio.

## Verification

Run the canonical gate from repo root:

```bash
PLAYWRIGHT_SKIP_BROWSER_GC=1 pnpm --dir web exec playwright install chromium
uv run devtools/gate.py
```

The first command provisions the browser needed by acceptance tests; `PLAYWRIGHT_SKIP_BROWSER_GC=1` preserves other projects' shared browser-cache versions. The gate builds `web/dist`, runs fixture servers, and regenerates test artifacts. It mocks inference and audio devices: passing it does not establish real-model speech quality, microphone behavior, or audible acceptance.

The gate validates `skills/voices-local-studio` without an installed
skill. Explicit standalone sync is separate from native plugin installation;
see [development guidance](devtools/README.md#packaging-and-deterministic-gate).

## License and assets

Original code/docs are [MIT licensed](LICENSE); [notices](NOTICE.md) identify separate terms. The UI build includes `THIRD-PARTY-LICENSES.md` for bundled dependencies. Python dependencies retain their own terms.

Model weights are separate downloads with their own licenses and model cards, selected by immutable revisions in `voices.config`. The source license grants no additional model, recording, voice-identity or likeness rights. Your saved voice library, recordings, reviews and generated audio are not distribution inputs.

Publish only [reviewed source/plugin exports](devtools/README.md#public-source-and-plugin-candidates), not Git history or the working directory.
