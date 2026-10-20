---
name: voices-local-studio
description: "Operate local Voices on this Mac: create/select/review voices, generate speech, transcribe an existing WAV, or align supplied text to audio. Not generic TTS/provider advice or skill-package authoring."
---
# Voices Local Studio

## Setup and lifecycle

This skill requires a local Apple Silicon Mac and an independently installed
`voices` CLI. It includes no cloud account, endpoint or model weights. Model
snapshots use disk and unified memory and retain their own licenses; installation
of this guidance downloads none. Use the repository's CLI setup instructions
when the command is missing, rather than bootstrapping a runtime from this skill.
Disabling or uninstalling the plugin leaves the CLI, model cache, library,
outputs and saved reviews intact and does not stop an already-running studio.

## Use when

- the user wants to operate the local voices product or CLI on this Mac
- the task is voice selection, voice design, imported clone review/save, record-to-clone, transcript review, creation-hub operation, playback review, spoken-output generation, audio-only transcription, or supplied-text alignment for that product
- the work needs local product state rather than generic upstream voice advice

## Do not use when

- the task is generic audio or speech guidance with no local product in scope
- the task is hosted/provider comparison, upstream Qwen advice, or generic TTS strategy without operating this local product
- the work is generic skill/package authoring, package maintenance, release proof, or repo development workflow; use the repo docs and package-quality skills instead
- the task belongs to a different local product

## Workflow

1. Resolve the installed CLI with `command -v voices`. Inspect its doctor identity and executable, not a presumed home-directory path or another project's Python environment.
2. Use the single installed CLI and standard shared Hugging Face cache. Do not provision a private checkout, Python/venv, duplicate model cache, or fallback; report an unavailable or mismatched installation concretely.
3. Use the bundled references below to explain the contract, not to substitute source inspection for the actual selected runtime. Missing installation or release repair belongs to the [Voices repository](https://github.com/Tiziano-AI/voices), not a guessed local checkout.
4. Start product operation with `voices --json doctor`. For saved-voice work, inspect with `voices --json list` and resolve candidates with `voices --json resolve`; transcription and alignment need no library selection.
5. For direct say, read, narrate, or render requests, choose an existing voice from `list` or `resolve`, then use `voices say` for local playback or `voices --json render` for saved output.
6. Launch the bundled UI with `voices ui` on a loopback host, and use ordinary process inspection only when cleanup is necessary.
7. `design` generates and saves a reusable library voice. A request to create a new voice, persona, or recurring narrator can cover that directly; an ordinary say/read/render request or a poor library match does not. If creation is needed but not covered, surface the choice between an available voice and creating a new one. Reserve `clone review`, `clone save`, `record`, and `delete` for their corresponding user intent; use `--dry-run` when available before writes or deletion.
8. For imported clone work, use `voices --json clone review` to create the review handoff, then `voices --json clone save` only after the operator accepts the audio/transcript.
9. In agent-harness record flows, run `voices --json record plan` first; ask language first; show the exact guided script plus duration for guided mode, or the exact stop rule for free mode, before capture starts.
10. For supplied-text timing, use `voices --json align` as described in [Operator Recipes](references/operator-recipes.md). This runs a model without capture/playback; require operator intent and never call alignment speech verification.
11. For recognition from an existing WAV, use `voices --json transcribe --audio <wav> --language English --model-revision <40-hex-sha>` with explicit inference intent. It accepts public language names such as `English` or `Italian`, not a supplied transcript, and returns recognition plus audio/model/runtime identity without creating a voice or review candidate. ASR evidence does not replace listening-quality acceptance; see [Operator Recipes](references/operator-recipes.md).
12. Studio **Save preview**, **Save clip**, **Save original clip** and **Save compared clips** retain exact preview bytes and their generation-time provenance. Noncurrent clips retain their original inputs; explicitly save the original rather than presenting it as current. CLI `render` or studio **Render export** without a preview generates a new performance. An expired token fails rather than substituting new audio; repeated save reuses the same pair. See [State and recovery](references/state-and-recovery.md) for failed takes and partial exports.
13. Verify the resulting output, saved voice, sidecar or blocking state against the selected runtime. Do not backfill older unknown provenance or treat upstream guidance as the local contract.

## References

- [Local Product Contract](references/local-product-contract.md)
- [Operator Recipes](references/operator-recipes.md)
- [Workflow Recipes](references/workflow-recipes.md)
- [Interactive Review And Playback](references/interactive-review-and-playback.md)
- [Record And Clone Workflow](references/record-and-clone-workflow.md)
- [STT Capability And Language Contract](references/stt-capability-and-language-contract.md)
- [State And Recovery](references/state-and-recovery.md)
- [Troubleshooting And Evaluation](references/troubleshooting-and-evaluation.md)
- [Prompt Authoring Recipes](references/prompt-authoring-recipes.md)
- [Upstream Capability Matrix](references/upstream-capability-matrix.md)
- [Voice Design Best Practices](references/voice-design-best-practices.md)
- [Voice Clone Best Practices](references/voice-clone-best-practices.md)
- [Review Scenarios](references/review-scenarios.md)
