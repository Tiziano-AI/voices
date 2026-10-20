# Voices Vision

## Outcome

`voices` is a local-first Apple Silicon voice studio for creating reusable reference voices, hearing real lines immediately, comparing options side by side, and exporting final speech on-device.

The durable library under `~/.voices` is the product memory that makes this loop repeatable. It is not the headline promise.

The canonical operator loop is:

- create or import a voice through `design`, `clone`, or `record`
- review the reference asset until it is trusted
- audition real lines immediately from the saved voice
- compare the same line across saved voices
- export final speech as WAV plus JSON provenance

## Primary users

- solo creators producing narration, character voices, and short-form spoken content
- developers and local-model users who want a scriptable on-device voice workflow
- operators maintaining a personal library of reusable reference voices under `~/.voices`

## Success criteria

- first success is complete: create or import one usable voice, audition a real line and keep the chosen WAV with provenance
- the CLI remains the canonical contract and automation surface
- the bundled local browser studio is the guided first-success surface for creation, audition, compare, and export
- the default library at `~/.voices` remains durable, legible, and recoverable
- persisted voice metadata remains explicit, validated, and stable enough for long-term local use
- transcript review, reference playback, and same-line compare make voice selection trustworthy instead of guess-driven
- voice creation and reuse work entirely on-device after the required model checkpoints are cached

## Non-goals

- hosted APIs, cloud sync, or remote multi-user serving
- speaker training pipelines, checkpoint fine-tuning, or model management beyond the supported MLX runtimes
- DAW-style editing, timeline composition, or batch post-processing
- heavy library-management suites such as tagging, favorites, archives, or version trees beyond the current inspect, compare, and delete scope
- permanent compatibility layers for retired schemas or duplicate product paths
