# Developing Voices

Run from the repository root. Keep operator assets and unrelated installed
tools intact. Check active consumers before replacing the global command's
environment. The repository's development environment is an editable install of
this checkout; the global command is not, and shares neither its source nor its
dependency environment.

External consumers use the one installed `voices` CLI and the standard shared
Hugging Face cache. Repository `uv run` is a development surface, not another
project's integration. Do not provision private source/Python/venv copies,
duplicate model caches, fallbacks or legacy backups. After verified replacement,
retire obsolete implementation paths; preserve user audio and provenance.

## Repository and global command

```bash
pnpm --dir web install --frozen-lockfile
pnpm --dir web build
uv sync --locked
uv run voices --json doctor
```

The global `voices` command is a non-editable `uv tool` install of a wheel
built from a committed revision, so nothing in this checkout reaches it until
it is reinstalled. Reinstalling is an explicit installation operation, not a
read-only diagnostic: resolve `command -v voices` and its receipt, check which
consumers are active (integrations may pin `runtime.source_sha256` and reject a
changed runtime), and install only committed source. Run the recipe from the
repository root; the subshell stops
at the first failing step, and it refuses a checkout with any uncommitted or
untracked change before building anything:

```bash
(
  set -euo pipefail
  if [ -n "$(git status --porcelain)" ]; then
    echo "voices reinstall: a clean committed checkout is required" >&2
    exit 1
  fi
  commit="$(git rev-parse --short=12 HEAD)"
  pnpm --dir web install --frozen-lockfile
  pnpm --dir web build
  uv build --wheel --out-dir ".tmp/dist-$commit"
  uv export --locked --no-dev --no-emit-project \
    --format requirements-txt --output-file .tmp/runtime-constraints.txt
  uv tool install --force --reinstall-package voices \
    ".tmp/dist-$commit"/voices-*.whl \
    --python "$(cat .python-version)" --constraints .tmp/runtime-constraints.txt
  voices --json doctor
)
```

Never install the global command with `--editable`: an editable global install
lets every source edit reach consumers at once.

The web build precedes Python sync because Hatch force-includes `web/dist`
even for editable installation. For a prebuilt wheel, install that exact wheel
with its matching exported runtime constraints; Node/pnpm and a source checkout
are not runtime dependencies. No installer downloads model weights or installs
an agent skill. Stop a running studio through its owning terminal before an
authorized replacement. `uv tool uninstall voices` removes the tool environment,
not the library, model cache, outputs, review files or separately installed
agent guidance. Do not delete those user assets as uninstall cleanup.

The `uv` receipt retains parsed exact constraints. A future global upgrade must
regenerate them from the new lock. Doctor's `runtime.executable` identifies
which environment actually ran. `runtime.source_sha256` fingerprints installed
Python source bytes at observation, not a Git commit or previously imported
bytecode. `runtime.packages` has the declared selected-dependency scope.
Doctor also reports the cache and immutable default model revisions; model
resolution must use full SHA snapshots, never mutable `refs/main`.
Do not upgrade unrelated global `mlx-audio`
or ambient Node installations to prove Voices is current.

## Snapshot and model-loader recovery

A directory containing all model files is not proof of offline Hub resolution.
Hugging Face Hub 1.30 also uses cached repository-tree inventory. After authorized
materialization through public `snapshot_download(repo_id=..., revision=...)`,
verify the pinned revision with offline mode. Do not hand-write cache metadata,
use mutable refs, duplicate caches or private provisioning fallbacks.

The ForcedAligner snapshot's top-level config declares `qwen3_asr`. The adapter
must call `load(snapshot_path, strict=True, model_type="qwen3_forced_aligner")`
and retain its concrete model check. A fake loader cannot catch wrong upstream
dispatch: exercise that dispatch with a faithful config fixture and the real
installed CLI before claiming alignment readiness.

## Packaging and deterministic gate

Build the UI first, then run `uv build`. Both distributions include generated
assets; the wheel selects `voices/web_dist`, not a checkout-relative bundle.
Verify a non-editable wheel's CLI and studio from outside the source module
path when changing packaging. Do not claim installation from a build alone.

```bash
PLAYWRIGHT_SKIP_BROWSER_GC=1 pnpm --dir web exec playwright install chromium
uv run devtools/gate.py
```

Browser provisioning must not garbage-collect shared revisions. The gate
rebuilds the UI and replaces browser test artifacts; preserve needed prior
evidence first. Model and audio-device paths are mocked in this gate.

The default gate validates the source skill, not a prior global installation;
its script checks use the same locked development toolchain as the repository.
Both Python-project and skill type checks use the npm Basedpyright package
through the web project's selected Node runtime, not a Python-distributed Node
binary. Run the project check separately with
`pnpm --dir web exec basedpyright --project ..`.
`uv run python devtools/sync_skill.py --check` is a separate read-only check for
an explicitly managed standalone skill. Plain sync replaces that installation;
it is not a prerequisite for testing and is not a native plugin installer.

## Distribution archives

This public repository is the development source. The exporter creates
reproducible ZIPs for source distribution or skills-only installation.

`skills/voices-local-studio` is the only skill source. The portable root
manifest and Claude manifest both discover it. Standalone sync remains explicit
for existing consumers; never run it as part of native plugin installation.
The installed CLI/wheel is independent. Native Git plugin installation fetches
the full developer tree but exposes only the skill, without installing the CLI
or its dependencies. The skills-only ZIP omits developer sources and tests.

The archives contain the committed revision. After committing the intended
changes, export to **new** paths:

```bash
uv run python devtools/export_public.py --kind source --list
uv run python devtools/export_public.py --kind source --output .tmp/voices-source.zip
uv run python devtools/export_public.py --kind plugin --output .tmp/voices-plugin.zip
```

The exporter reads regular blobs from HEAD and the committed exact-file
inventory `devtools/public-source-files.txt`. Uncommitted/untracked changes,
history, recovery stores, state, audio, model weights and historical
`docs/releases/` records cannot enter through a directory sweep. Only the
reviewed Voices SVG and its PNG logo are admitted as visual assets. Additions
require an intentional inventory edit. Archives have fixed ordering, modes and timestamps;
repeated exports of one commit are byte-identical and never overwrite a path.
Plugin export omits skill developer tests/config, includes MIT/notices and uses
`PLUGIN.md` as its root `README.md` instead of the developer-source README.

The source ZIP is a clean developer tree, not a clone or a backup. Extract it,
build the web bundle, then run Python setup/gate normally. The runtime sdist is
narrower: runtime source and metadata plus the built web bundle, with its
generated dependency notices. Neither artifact contains a model or user audio.
Review the exact archive contents and applicable rights before redistributing
them. The inventory controls ZIP membership; it is not a secret scanner or a
review of Git history.

Validate `plugin.json` against the declared Agent Plugins schema and run
`claude plugin validate` on the extracted plugin. Exercise discovery,
enable/disable and removal in disposable host configuration roots, not live
settings. Structural validation does not establish model routing or audible
quality. Do not create a live catalog entry or install globally for these tests.

For revision/provenance changes, inspect a new installed-CLI render sidecar,
not just doctor or old artifacts. Older sidecars keep unknown fields; never
backfill them with today's runtime. For `voices --json align`, verify original
audio hash, exact supplied text, model revision/runtime and ordered bounded
word times. Alignment is supplied-text estimation with `spoken_content_verified`
false, not independent speech verification. Keep estimator adjustments and
missing raw correction diagnostics explicit.

## Opt-in real models

Optional DGX source qualification uses the same CLI/loopback studio with an
isolated library, outputs and `--compute-state`, existing SSH, retained pinned
checkpoints and the two CUDA overlays. Do not install the MLX-dependent wheel
on DGX or run the downloading MLX qualification below as a substitute. Exercise
design/review/save, Base with different text, exact-preview repeated export,
independent ASR and separate alignment; keep cancellation/publication and
disconnect/recovery separate from GPU interruption. Preserve invocation identity
and settle naturally before operator-owned retained-lane restoration. Generated
audio/transcripts and private receipts are not public source or quality votes.
Source development does not update the globally installed command.

Only with explicit intent for model downloads, inference, and new test assets:

```bash
uv run devtools/qualify_runtime.py --out .tmp/qualification-NEW --parallel
```

Choose a new root. This exercises Italian/English VoiceDesign, Base synthesis,
ASR review, a synthetic clone, long passages, repeated calls and optionally
concurrent callers through the process-global MLX guard. It does not capture a
microphone or play speakers. Outputs stay under that root, never `~/.voices`.

The report retains inputs, actual audio-only ASR, waveform/timing measurements
and WAV/JSON paths. Word error rate measures ASR disagreement, not an
independent guarantee of spoken completeness, pacing or timbre. Listen before
claiming human audio acceptance. Exit zero means the measurement run finished,
not that every voice sounds good.

Existing roots are refused. After an interruption, inspect `events.jsonl`,
`report.json` and persisted artifacts before choosing another action. A new
run is a new occurrence, not recovery of the previous output.
