# Voices agent plugin

**Publisher:** Tiziano AI · [source and CLI setup](https://github.com/Tiziano-AI/voices)
· **License:** MIT for original code and guidance; see `NOTICE.md`.

Create reusable reference voices, review recordings, audition and compare real
lines, and keep the exact performance you selected as WAV plus provenance.
The package adds one skill, `voices-local-studio`, to a host with local shell
access. It is not a hosted speech service.

## Before installing

- You need an **Apple Silicon Mac**, a separately installed `voices` CLI and
  your own model snapshots. Python/MLX, FFmpeg for recording/import, and the
  runtime's other requirements belong to the CLI installation.
- Plan disk space and free unified memory for local model inference. Consult
  the selected model's requirements; no minimum-memory configuration has been
  independently qualified by this project. There is no cloud fallback.
- Qwen/MLX weights and their licenses are separate from the plugin. First
  authorized model use may download a pinned snapshot from Hugging Face.
- No cloud endpoint, account, subscription, model weights or installed CLI is supplied.
  Plugin installation does not run a setup script, downloader, hook, MCP server,
  microphone capture, playback or inference.

Install the CLI independently using its source/build instructions, then resolve
`command -v voices` and run `voices --json doctor`. Doctor inspects setup without
loading a model; it does not prove inference or audible quality. Keep model
downloads and recording explicit, separate choices.

## Use and removal

Ask your agent to use Voices to inspect saved voices, create a synthetic voice,
review an authorized recording, or render speech. The skill resolves the CLI
from `PATH`; it never guesses the publisher's checkout or supplies another
Python environment. Its prompt workbench is bundled, standard-library-only
Python and does not run models.

Disabling the plugin stops its guidance from being offered to new work;
an already-open chat may retain instructions. Uninstalling removes the
host-owned plugin, **not** the independently installed CLI, `~/.voices`, your
output directories, saved reviews or shared Hugging Face model cache. It does
not stop a running `voices ui` process or inference already accepted by it.
Stop the studio in its owning terminal. CLI removal and deliberate user-data
deletion are separate operations; plugin removal never performs either.

Do not install both native and standalone copies of this skill in the same
host: choose one discovery owner. The repository's standalone sync is not a
plugin installer and must not write into a host's plugin cache.

## Package contract

Root `plugin.json` declares Agent Plugins 1.0.0 and OpenAI presentation metadata;
`.claude-plugin/plugin.json` supplies Claude Code identity. Both discover the
same `skills/voices-local-studio/` directory. There are no settings, service
registrations, permissions overrides or automatic effects.

Native catalog installation fetches the repository's complete developer tree
but exposes only this skill; it does not install the CLI or its dependencies.
The separately exported skills-only ZIP omits the developer sources and tests.

Release maintainers export the plugin or curated tool source with
`devtools/export_public.py`; those archives are not a copy of Git history or
the operator's working directory. See the repository's development guide.
