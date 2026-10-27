<img src="skills/voices-local-studio/assets/voices.png" width="72" height="72" alt="">

# Voices

Create reusable voices, try real lines, and keep the performance you like.
Voices runs Qwen3-TTS on your Apple Silicon Mac through MLX, with a browser
studio for listening and comparison and a CLI for scripting.

Design a synthetic voice or import a recording you have permission to use.
Saved voices are reference audio and transcripts, not trained models. Speech
exports are WAV files with JSON provenance; the studio can save the exact
preview you heard rather than generating it again.

[Setup](#setup) · [First saved result](#first-saved-result) ·
[Commands](#command-reference) · [Agent plugin](PLUGIN.md) ·
[Development](devtools/README.md)

## Requirements

- Apple Silicon Mac
- Python `>=3.14.10,<3.15` ([security fixes](https://www.python.org/downloads/release/python-31410/)); `.python-version` selects `3.14.10`
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [pnpm](https://pnpm.io/installation) and Node.js for source builds; `web/package.json` selects their versions
- FFmpeg on `PATH` for audio import/review, recording, `transcribe` and `align`

Model snapshots also need disk space and free unified memory. Check the
selected model's requirements; this project has not qualified a minimum-memory
configuration. Inference stays local, with no cloud fallback. Missing models
may download from Hugging Face when first used; their licenses apply separately.

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

`uv run voices` uses this checkout. A separately installed global `voices`
command does not change when you edit source or run `uv sync`; see
[global installation](devtools/README.md#repository-and-global-command).
Models use pinned, immutable revisions in the standard shared Hugging Face cache.

## First saved result

Start by checking setup, then open the studio:

```bash
uv run voices --json doctor
uv run voices ui
```

Doctor checks readiness without loading a model. In the studio:

1. Choose **Design** and describe an original voice.
2. Save the voice, enter a line you actually want to use, and preview it.
3. Listen, then choose **Save preview** to keep that exact WAV and its JSON sidecar.

Stop the studio with Ctrl-C in its terminal. Unsaved previews are temporary;
saved voices live under `~/.voices` and exports under `./outputs` by default.

For the same path in the terminal, preview the proposed voice with `--dry-run`,
then create it and render a line. These generation commands may download models:

```bash
uv run voices design --id studio_narrator --name "Studio Narrator" --language English \
  --instruct "A calm adult narrator, clear diction, natural pacing, no theatrical emphasis." \
  --text "A small idea becomes useful when someone can put it to work." --dry-run
uv run voices design --id studio_narrator --name "Studio Narrator" --language English \
  --instruct "A calm adult narrator, clear diction, natural pacing, no theatrical emphasis." \
  --text "A small idea becomes useful when someone can put it to work."
uv run voices --json render studio_narrator "This is a line worth keeping."
uv run voices --json outputs list --voice studio_narrator
```

CLI `render` generates a new performance; it does not recover a studio preview.
Installation starts no inference or microphone capture. Removing the CLI or
plugin preserves your voice library, renders, reviews and model cache.

## Agent plugin

The [Voices plugin](PLUGIN.md) packages `skills/voices-local-studio` for Agent
Plugins and Claude Code. Install CLI/models independently; the plugin runs no
setup, hook, downloader or MCP server. Removal preserves CLI, cache and audio.

## Command reference

### `ui`

Launch the bundled local browser studio.

```bash
uv run voices ui
uv run voices ui --library ~/.voices --port 9901 --no-open
```

The studio shares CLI workflows and storage and accepts only loopback hosts
(`127.0.0.1`, `localhost` or `::1`). Stop it in the terminal that launched it.
If bundle assets are missing, rebuild the UI or reinstall the wheel; launch
does not build them. Request admission is described in [architecture](ARCH.md#local-http-contracts).

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
```

Listen to the normalized WAV and check the review JSON's `transcript` against
it. Correct the draft if needed, then save the approved reference:

```bash
uv run voices --json clone save \
  --review ./matteo-review.json \
  --id matteo \
  --name "Matteo"
```

- `ffmpeg` must be available on `PATH`
- `--transcript` seeds the review draft when you already have a correct transcript; when omitted, local STT creates the draft
- `clone review` writes the draft and a normalized WAV sibling; `clone save` does not add another transcript-approval prompt
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
- `--name` must be non-empty after trimming; when `--id` is omitted and `--overwrite` is set, `record` overwrites the slug derived from the approved name instead of creating a suffixed new id
- `ffmpeg` must be available on `PATH`
- `record plan` reports the guided script, target duration, free-mode minimum, and stop rule without using the microphone

### `say`

Speak immediately through macOS speakers.

```bash
uv run voices say "We proceed at dawn." --voice noir_narrator
```

- `--voice` is optional; when omitted, `say` uses the most recently created saved voice
- an empty library needs a reference from `design`, `clone review`/`clone save`, or `record` before speech can be generated
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
```

Preview a deletion before confirming it:

```bash
uv run voices delete noir_narrator --dry-run
uv run voices delete noir_narrator --yes
```

- `list` shows `id`, `lang`, `source`, and wrapped `desc`
- `list` filters by `--language`, `--source`, `--query`, and `--limit`
- `resolve` returns one exact or unambiguous saved `voice_id`
- `show` prints the full persisted metadata plus derived `description` and `source_kind`
- `outputs list` reads persisted render sidecars under `./outputs/<voice_id>/`
- `outputs show` accepts either a WAV or JSON sidecar filename and returns the persisted output metadata plus artifact paths
- `delete --dry-run` reports the voice that would be deleted without removing files
- `delete --yes` removes a saved voice without an interactive confirmation step

## Bundled browser studio

The studio opens with a creation path when your library is empty. With saved
voices, choose a reference, enter a line and audition it; use the Audition Board
to compare the same line across voices and retain individual performances.

- **Design**, **Clone file** and **Record live** share the CLI's voice library.
- **Save preview**, **Save clip** and **Save compared clips** keep the WAVs you
  heard and their original provenance. Retrying a save reuses its output pair;
  an expired preview fails rather than being synthesized again.
- Editing inputs keeps earlier clips and links. **Save original clip** explicitly
  retains a performance that no longer matches the current inputs.
- If a comparison fails for one voice, the other clips remain playable and
  saveable. **Retry** generates only the failed inputs, keeping successful clips
  and downloads. Changed inputs generate the missing current performances.
- Removing the last saved voice keeps session clips, board cards and downloads
  accessible; select or create a voice before generating new audio.
- **Render export** without a preview generates a new performance.
- Unsaved previews, compare clips and board positions last only for the session.

If transcript review fails after recording, **Retry review** uses the same take
and **Download take** keeps its bytes. Resetting or closing the panel discards
that unsaved take. Closing also stops active microphone tracks; it cannot dismiss
a pending browser or operating-system permission prompt.

Closing a panel or aborting a request does not undo a save the server already
accepted. Inspect the library before retrying an interrupted save. See
[performance identity](docs/performance-identity.md) for freshness, input conflicts
and export behavior, and [architecture](ARCH.md) for storage and HTTP contracts.

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

`examples/prompts/basic.jsonl` is a neutral two-voice starter pack. Preview the
proposed voices with `design-batch --dry-run` before generating audio.

## Development

[Architecture](ARCH.md) describes the implementation boundaries and persisted
formats; [product scope](VISION.md) records the intended workflow and non-goals.
The [development guide](devtools/README.md) covers global installation, packaging,
model-cache recovery and opt-in real-model qualification.

`.codex/environments/environment.toml` supplies optional top-bar actions:
`Setup`, `Run Studio`, `Doctor`, `Build UI`, `Gate`, `Python Tests`, `Web Checks`
and `List Voices`. Setup follows the build-before-sync order above. These are
CLI conveniences, not a separate API; parameterized, destructive, audio-device
and model-heavy operations remain explicit commands.

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

For reproducible source or skills-only ZIPs, see
[distribution archives](devtools/README.md#distribution-archives).
