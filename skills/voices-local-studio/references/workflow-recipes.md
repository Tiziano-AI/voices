# Workflow recipes

## Direct "say this" request

Use when the user wants the agent to read a line, narrate a summary, or speak text with the local product.

Sequence: run `voices --json doctor`, inspect saved voices with `voices --json list`, resolve a suitable existing voice with `voices --json resolve`, then use `voices say` for local playback or `voices --json render` for a saved artifact. If none fits, surface the actual choice: use the closest available voice or create a new reusable one. An empty library requires creation before speech, not silent permission to create. Return transcript, voice id, and output path when a file is rendered.

## Design one voice

Use when the user wants a new fictional, stylized, or persona-driven voice. `design` generates a reference and saves it in the library; it is not an ephemeral speaking style. A request to create a persona or recurring narrator can authorize this naturally, without a separate confirmation ritual.

Sequence: author a structured spec, compile with the workbench, run `voices design`, review with `say`, `render`, or UI, then iterate one variable at a time.

## Build a themed prompt pack

Use when the requested outcome includes creating multiple distinct voices around one concept, not merely comparing existing voices.

Sequence: scaffold, vary at least two dimensions per entry, compile JSONL, audit, then run `voices design-batch`.

## Choose design vs clone

These are creation-path choices once a new reusable voice is in scope, not fallbacks from an ordinary speaking request.

Use `design` when:

- the target is a persona
- there is no clean source speaker
- style flexibility matters more than identity capture

Use `clone` when:

- a real speaker identity matters
- clean audio exists
- the transcript is reliable

Use `record` when:

- the operator wants the product to capture the reference clip directly
- there is no prepared audio file yet
- you still want the saved result to become a normal reusable clone voice

For `record` and transcript-assisted clone work, capture or upload audio, play the take, inspect the STT draft, accept/retry/edit/replay, and save only after the operator approves audio and transcript. Use `clone review` plus `clone save` for imported audio and `record plan` before interactive microphone capture.

## Choose an existing voice vs design a new one

Prefer an existing saved voice when:

- it already matches the task’s purpose, pace, and authority or warmth
- the user did not ask for a new persona
- the task needs speech rather than another library asset

When creation is part of the requested outcome, design a new voice when:

- no saved voice fits the task cleanly
- the task needs a distinct persona, brand tone, or recurring narrator
- the existing library is close in style but wrong in emotional temperature or purpose

Those fit problems can justify proposing creation; they do not by themselves authorize saving a voice. If creation is not already covered, explain the available-voice versus new-voice choice before running `design`.

## Task-fit voice heuristics

Useful starting points: calm authority and measured pace for product summaries;
crisp articulation and medium energy for technical demos; restraint and precision
for operational reads; brighter delivery without caricature for promotional work.
Let the actual text and intended listener decide. For fiction, choose a close
saved voice or design a new one when character creation is part of the request.

## Use `say` vs `render`

Use `say` when:

- you need fast ephemeral audition
- you are tuning a prompt live
- the user wants immediate local playback and does not need a file

Use `render` when:

- you need a WAV file to keep or hand back
- generation-time provenance in the JSON sidecar matters

## Use the UI

Use the UI when:

- comparing multiple saved voices quickly
- previewing references
- selecting multiple voices for one text
- exporting per-voice outputs after render
- creating a voice through the bundled `Design`, `Clone file`, or `Record live` hub
- reviewing recorded or imported takes with explicit playback before approving the transcript

The UI is helpful for browse-and-compare loops. The CLI remains canonical for controlled generation and scripting.

Studio lifecycle:

- start with `voices ui` on the desired loopback host and port
- use the terminal session that launched `voices ui` as the process owner
- if the port is already occupied, stop the owning process or choose another loopback port
- do not invent `ui status`, `ui stop`, runtime lock files, or `/api/health` checks; the current product does not expose them
