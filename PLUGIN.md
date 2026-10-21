# Voices agent plugin

**Publisher:** Tiziano AI · [source and CLI setup](https://github.com/Tiziano-AI/voices)
· **License:** MIT for original code and guidance; see [notices](NOTICE.md).

Create reusable reference voices, review recordings, audition and compare real
lines, and keep the exact performance you selected as WAV plus provenance.
The package adds one skill, `voices-local-studio`, to an agent host with local
shell access. The speech runtime is a separate installation on your Mac.

## Before installing

- You need an **Apple Silicon Mac**, a separately installed `voices` CLI and
  model snapshots. Python/MLX, FFmpeg for recording/import, and the
  runtime's other requirements belong to the CLI installation.
- Plan disk space and free unified memory for local model inference. Consult
  the selected model's requirements; no minimum-memory configuration has been
  independently qualified by this project. There is no cloud fallback.
- Qwen/MLX weights and their licenses are separate from the plugin. First
  authorized model use may download a pinned snapshot from Hugging Face.
- This is guidance, not a cloud service or CLI installer. Installing it runs no
  setup, downloader, hook, MCP server, microphone capture, playback or inference.

Install the CLI independently using its source/build instructions, then resolve
`command -v voices` and run `voices --json doctor`. Doctor inspects setup without
loading a model; it does not prove inference or audible quality.

## Try it

- “Find a saved voice that would suit this narration.”
- “Create an original, calm narrator and let me compare a few lines.”
- “Render this text with my selected voice and keep the WAV.”

Creating a voice saves a reusable reference. An ordinary speech request uses
an existing voice; cloning and microphone recording require that specific intent.

## Use and removal

The skill resolves the CLI from `PATH` and checks the selected installation.
Its bundled prompt workbench uses only Python's standard library and runs no models.

Disabling the plugin removes its guidance from new work; an open chat may still
retain it. Uninstalling removes the host-owned plugin while preserving the CLI,
`~/.voices`, outputs, saved reviews and the shared Hugging Face cache. A running
studio or accepted inference continues independently; stop the studio in its
owning terminal. CLI removal and user-data deletion are separate operations.

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

See [distribution archives](https://github.com/Tiziano-AI/voices/blob/main/devtools/README.md#distribution-archives) for
reproducible source and skills-only ZIPs.
