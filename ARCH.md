# Voices Architecture

## Canonical product shape

`voices` is a local-first studio with one durable voice library.

- Public/machine contract: `voices` CLI
- Guided studio: `voices ui`
- Library: `~/.voices`
- Outputs: `./outputs`

The loop creates/imports a reference through `design`, `clone` or `record`, reviews it, auditions lines and exports WAV/JSON provenance.

`voices.edge` owns loopback HTTP, `web/` browser rendering, and `voices ui` launch. No hosted API, remote serving, or alternate persistence exists.

## Runtime compatibility and source contracts

Python manifests/lock and `web/package.json`/`web/pnpm-lock.yaml` own dependency selections.

- External consumers invoke the single installed `voices` CLI. They do not own a second Voices checkout, Python/venv, model cache, provisioner, or fallback. The standard Hugging Face cache is shared; source development remains in this repository.
- `voices.adapter.model_snapshot` resolves full 40-hex revisions, never mutable `refs/main`. `voices.config` owns pinned Base, VoiceDesign, ASR and ForcedAligner defaults. Render and align permit explicit revisions; transcribe requires one. Design and clone/record STT use configured defaults.
- `mlx_qwen` loads the resolved snapshot, supplying Base `text/ref_audio/ref_text/lang_code` or VoiceDesign `text/instruct/language`. `_collect_audio` exhausts all generator chunks and post-yield cleanup under `serialized_mlx_runtime()`. Loading, generation, STT, alignment and cache clearing share that process-global lock.
- Base consumes captured bytes and clears the weak upstream ICL cache under that lock; [performance identity](docs/performance-identity.md) owns the capture/decoder/cache contract.
- `mlx_stt` maps audio-only `STTOutput`; `mlx_align` estimates supplied-text times, not spoken-content verification. Its snapshot loads with `strict=True, model_type="qwen3_forced_aligner"`; config otherwise dispatches to ASR. No tokenizer monkeypatch, separate `mlx-lm`, or parallel MLX path.
- `voices.runtime_identity.RuntimeIdentity` owns runtime/source provenance. The digest covers installed Python bytes observed before generation, not Git or previously imported bytecode. Package identity covers selected dependencies, not the whole environment. Historical unknowns remain unknown.
- Typer vendors Click: `cli_entrypoint` handles Typer's actual exception classes, not unrelated standalone Click classes. `cli_json`/`cli_support` separate JSON stdout from diagnostics.
- Native pnpm `packageManager` and `devEngines.runtime` select the web runtime without replacing ambient tools. Basedpyright runs from that same Node development graph against the root Python project; no Python-distributed Node binary is installed.
- `ffmpeg_audio` owns FFmpeg capture; `useRecorder` owns browser capture. `edge.app` explicitly dispatches synchronous workflow calls through Starlette `run_in_threadpool`; the shared MLX lock still serializes inference.
- Free CLI capture has one lexical owner, `ffmpeg_audio.free_recording`: cooperative stop, forced retirement when necessary, child collection and pipe closure precede every exit. EOF/interrupt abort only after cleanup; a forced or failed stop never enters review. Guided capture retains `subprocess.run` ownership.
## Boundary owners

| Boundary | Owner | Contract |
| --- | --- | --- |
| CLI ingress | `voices.cli`, `voices.cli_diagnostics`, `voices.cli_library`, `voices.cli_speech`, `voices.cli_create`, `voices.cli_clone`, `voices.cli_outputs`, `voices.cli_record`, `voices.cli_edge`, `voices.cli_align`, `voices.cli_transcribe` | Typer args and global output mode enter workflows and return human or JSON output. `voices.cli` owns the root app and callback; feature modules register commands. `voices.cli_edge` owns the read-only `edge get` probe. |
| CLI JSON envelope | `voices.cli_json` | Owns `--json`, stdout JSON, and product-error envelopes. |
| CLI human helpers | `voices.cli_support`, `voices.cli_review` | Own terminal rendering, playback, prompts, transcript approval, and human exits. |
| Local HTTP ingress | `voices.edge.app`, `voices.edge.local_admission` | Own loopback request admission, responses, browser JSON contracts, and browser-safe errors. |
| Studio orchestration | `voices.edge.service`, `voices.edge.storage` | Own edge contract mapping, temp previews, review tokens, and temp asset cleanup. |
| Browser studio | `web/src` | Owns launchpad, voice rail, audition workbench, Audition Board, transport/inspector, creation sheet, and palettes. `useStudioController` composes bootstrap, selection, freshness, and specialized owners; `useAudioSession` owns playback; `useAuditionBoard` owns candidates, stale/render state, and positions; `useRecorder` owns microphone acquisition, capture, metering, timers, and cleanup; `studioControllerTypes` owns the envelope; `StudioShell` owns composition only. |
| Studio bundle | `voices.studio_bundle`, `pyproject.toml` build targets | Select installed `voices/web_dist` or editable `web/dist`; package generated assets in wheel and sdist. Missing assets fail before launch; runtime never builds them. |
| MLX adapters | `voices.adapter.mlx_runtime`, `voices.adapter.mlx_qwen`, `voices.adapter.mlx_stt`, `voices.adapter.mlx_align`, `voices.adapter.model_snapshot` | Own immutable snapshot resolution, serialized inference and typed outputs. |
| Runtime identity | `voices.runtime_identity` | Own selected dependency and source-byte identity, shared by doctor and generation-time provenance. |
| Alignment contract | `voices.domain.alignment_contracts` | Own audio/text/model identity, word timings, and explicit non-verification semantics. |
| Transcription contract | `voices.domain.transcription_contracts`, `voices.domain.audio_contracts` | Recognized text/model/runtime; shared audio identity. No library writes. |
| Audio adapter | `voices.adapter.ffmpeg_audio` | Owns import normalization and FFmpeg microphone capture. |
| Stores | `voices.store.library_store`, `voices.store.output_store` | Own schema-v2 voice assets and render artifact writes, reads, and path lookup. |
| Workflows | `voices.workflow.design_voice`, `voices.workflow.clone_voice`, `voices.workflow.synthesize_voice`, `voices.workflow.align_speech`, `voices.workflow.transcribe_speech` | Own design, clone review/save, synthesis, supplied-text alignment, and independent audio-only recognition. |
| Operator skill | `skills/voices-local-studio` | One canonical skill for portable/Claude plugins and explicit standalone sync; dev/release proof stays in docs/devtools. |
| Public archives | `devtools/export_public.py`, `devtools/public-source-files.txt` | Export only named regular blobs from HEAD, excluding history, local state, historical release records and unadmitted media. |
| Codex projection | `.codex/environments/environment.toml` | Owns app top-bar setup, build, gate, and safe CLI actions only. |

## Operator skill package

Root `plugin.json` and `.claude-plugin/plugin.json` discover the same
`skills/voices-local-studio` package. It resolves the installed CLI through PATH
and scripts relative to its host-provided root, not a personal checkout. The
gate validates source independently of installed guidance; `devtools/sync_skill.py`
owns explicit standalone parity/sync, including modes and metadata, ignoring
regular `.DS_Store`. Plugin removal preserves CLI, models and user assets.
`PLUGIN.md` and `devtools/README.md` own packaging and installation details.

## Codex local environment projection

`.codex/environments/environment.toml` projects safe zero-argument actions,
not another product API. Its setup builds the web bundle before `uv sync`;
Hatch includes it even for editable installs. `README.md` lists the exact
actions and effects; `tests/test_codex_environment.py` checks them. Parameterized,
destructive, audio-device and model-heavy operations remain explicit CLI work.
The Vite license report travels with the bundle in wheel and sdist.

## Persisted contracts

### Voice library root

- Default library path: `~/.voices`
- Override precedence: `--library` > `VOICES_LIBRARY` > default. Every CLI/UI ingress expands `~` and resolves the selected root to one absolute local path before reads, writes, or JSON path projection.
- `voice_id` grammar: `^[a-z0-9]+(?:[-_][a-z0-9]+)*$`

### Per-voice layout

`voice.json` stores schema v2 fields: `id`, `name`, `created_at`, `language`, `base_model_id`, `reference_text`, `reference_sha256`, and `source`. Design sources store `kind="design"`, `model_id`, and `instruct`; clone sources store only `kind="clone"`.

The disk contract owns `reference.wav` and `reference.txt`. `voice.json` does not duplicate those fixed filenames.

Persisted voice saves are staged inside the canonical library parent and swap into `~/.voices/<voice_id>/` only after `reference.wav`, `reference.txt`, and `voice.json` are durable. Overwrite never deletes the previous saved voice before the replacement is durable.

Saved-library entries are real directories under the canonical library root. Symlinked voice directories are invalid for load, save, overwrite, and delete. Assets are regular files only. Missing assets, malformed metadata, mismatches, directories in place of files, or symlinked assets are corruption and fail closed.

`load_voice_snapshot` owns coherent descriptor-based capture through consumption; HTTP audition returns captured bytes too. See [performance identity](docs/performance-identity.md).

Non-hidden occupants at `~/.voices/<voice_id>` must be real directories. A plain file, device, or other non-directory entry at that canonical path is library corruption during reads and an invalid overwrite target during saves. The library never silently skips those occupants.

### Render output sidecar

Sidecars retain schema v2: `voice_id`, `created_at`, `language`, `base_model_id`, `text`, canonical WAV basename `output_audio`, `reference_voice_id`, `reference_sha256`, `reference_text_sha256`, `base_model_revision` and `runtime` generation-time identity. New drafts require the transcript digest, computed over the effective UTF-8 transcript. Older sidecars lacking these provenance fields stay unchanged and read as unknown/null; current environment facts must not be backfilled into historical artifacts.

No persisted output metadata stores fake relative paths back to the voice library.

Output basenames are `<timestamp>__<slug>`, with `-2`, `-3`, etc. for collisions. The store reserves WAV and JSON names together; an orphan sidecar is a collision, not overwriteable debris.

Render publication is serialized per `./outputs/<voice_id>/`; concurrent renders reserve one basename and publish either `<timestamp>__<slug>.{wav,json}` or the next `-N` pair. Sidecar names and `output_audio` must be matching canonical basenames. The output root, per-voice directory, and requested file must be real local paths; symlinks, non-directory owners, broken symlinks, and noncanonical artifact names fail closed.

## CLI projection contracts

- `voices --json <command>` is the one machine surface. Success and product-domain failures emit one JSON document to stdout; progress, diagnostics, playback prompts, and Rich output never share stdout. Collections return `items/count/limit`, reads canonical models/paths, writes `voice` or `artifact`/paths, and errors `error.code/message/exit_code`.
- `voices doctor` replaces readiness/status and never loads models. It reports `auth_required=false`, library precedence `--library > VOICES_LIBRARY > ~/.voices`, effective library and voice count, output root, studio bundle readiness, FFmpeg readiness, runtime identity including source SHA-256 and selected package versions, and configured model IDs/revisions.
- Read/discovery commands are `languages`, filtered `list`, `resolve`, `show`, `outputs list`, and `outputs show`. `resolve` accepts exact id, exact display name, or one unambiguous fuzzy id/name/description match.
- Write/playback commands are `design`, `design-batch`, `render`, `say`, and `delete`. `design`, `design-batch`, and `delete` support dry runs; render writes a schema-v2 sidecar and WAV.
- `render --model-revision` pins a full 40-hex Base revision. `align` uses Qwen3-ForcedAligner for supplied-word times, never spoken-content verification. `transcribe` requires WAV, public language and explicit ASR revision, recognizing without supplied text. [Existing-audio inference](docs/audio-inference.md) owns their JSON fields, shared audio identity, validation, dependencies and claim limits.
- Clone import is explicit: `clone review --audio ... --review-out review.json` writes review JSON plus normalized WAV; `clone save --review ... --id ... --name ...` is the only CLI persistence step for imported clone reviews.
- `record` remains interactive FFmpeg `avfoundation` microphone capture and saves a normal clone voice after transcript/playback review. `record plan` is the non-interactive script/timing/stop-rule read; JSON mode does not start capture.
- `ui` is the loopback-only studio. It shares CLI workflows and keeps unsaved previews and board positions ephemeral. Close/path switch invalidates browser observation, not server-side persistence. Design checks cancellation before each save; earlier saves are not undone. Reconcile library state before replaying an interrupted save.
- Browser state orchestration is split by owner: `useStudioController` composes bootstrap, selection and creation flows; `usePerformanceSession` owns stage preview/compare/export occurrences; `useAudioSession` owns playback and enters `playing` only after `HTMLAudioElement.play()` resolves; `useAuditionBoard` owns session-only performance cards, attempts, exports and positions; `useRecorder` owns capture, consumed by `RecordPane`. The shell owns no network, audio, capture, or persistence decisions.
- [Performance identity](docs/performance-identity.md) owns browser freshness, target coverage, attempt/export identity and preconditions.
- Each recorder permission request has one capture identity. Reset/unmount invalidates it; a late stream is stopped before encoder/meter setup, and a late rejection cannot replace newer state. Cleanup detaches recorder callbacks, stops an active encoder, retires every track, and closes the audio context. The browser cannot dismiss a pending operating-system permission prompt.
- `RecordPane` consumes captured bytes only after transcript review succeeds. Failure retains the same Blob for explicit review retry or download, without new capture. Reset/close discards that unsaved panel-local take; it is not crash recovery. Capture language/mode/script are locked while permission, capture or retained-take processing is active.
- CLI `render` and studio **Render export** without a preview synthesize a new performance. **Save preview**, board **Save clip** and **Save compared clips** promote the selected preview WAV bytes, with its original generation-time draft. `StudioAssetStore` retains that draft and one export path per token; concurrent/repeated exports reuse the same pair. Expired/unknown/review tokens fail without resynthesis. Partial compare saves retain successful downloads and allow retry.
- Human `list` renders `id`, `lang`, `source`, and `desc`; empty libraries point to `design`, `clone review` plus `clone save`, and `record`. Human `show` renders full metadata plus derived description/source/path fields.

## Canonical audio review path

After any non-design ingress produces an audio file, both the CLI and the browser studio must call the same post-capture review owner: `voices.workflow.clone_voice`.

- `review_policy="import"` covers imported clone audio and does not enforce an extra minimum duration
- `review_policy="record_guided"` covers guided recording and reuses the same transcript-review and save path without an extra minimum
- `review_policy="record_free"` covers free recording and enforces the product minimum before transcript review is allowed
- the only legal persistence step after review is `clone_reference_voice`, so `record` and `clone` save the same persisted voice kind
- browser review tokens are single-spend. The save path claims one token exclusively before persistence, releases that claim only when persistence fails, and retires the token plus temp audio immediately after one successful save so concurrent saves cannot duplicate one approved take

## Local HTTP contracts

`voices.edge.app` owns local HTTP validation and maps runtime failures into JSON error envelopes. Synchronous model, FFmpeg, STT, and filesystem work explicitly enters Starlette's threadpool. MLX load/TTS/STT and generator completion use the shared `voices.adapter.mlx_runtime` lock; the local Metal runtime is process-global.

Every route requires one loopback `Host` on the actual ASGI socket port; mutations permit no `Origin` or one complete `http://` loopback origin on that port. Strict grammar rejects malformed/duplicate authorities before effects. The launcher disables proxy headers; [performance identity](docs/performance-identity.md) details admission.

Multipart uploads are bounded by `config.MAX_UPLOAD_BYTES`. The edge rejects oversized multipart `Content-Length` values before form parsing when the browser supplies them, then prompt-pack and clone-review uploads stream through the same capped temp-file owner.

Pydantic/FastAPI validation and Starlette parser HTTP 400 errors share the browser validation envelope. Starlette owns URL-encoded form limits (1,000 fields, 1 MiB per field), including requests without Content-Length; upload validation runs after this parser.

Read routes expose UI config, ordered voice summaries, full voice detail, and saved reference audio.

Preview responses carry effective `input`; browser requests carry reference/model preconditions, checked before inference (409 on preview/render conflict). Compare returns ordered per-voice `clip`/`error` outcomes, preserving successes through another voice's failure. The exact wire contract is in [performance identity](docs/performance-identity.md).

Mutation routes own preview/compare, render, `POST /api/previews/{token}/export`, design/batch design, clone/record review, single-spend clone save, and deletion. Preview export copies through the same locked WAV/sidecar publisher as render; only render synthesizes. `record_free` review enforces its minimum before save.
