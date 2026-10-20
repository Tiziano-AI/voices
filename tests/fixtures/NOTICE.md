# Upstream ForcedAligner configuration fixture

`qwen3_forced_aligner_53c8c0e_config.json` reproduces `config.json` from
[`mlx-community/Qwen3-ForcedAligner-0.6B-bf16`](https://huggingface.co/mlx-community/Qwen3-ForcedAligner-0.6B-bf16)
at immutable revision `53c8c0e46733eec430e4b53dd6471d0e5dee45f8`.
The [pinned model card](https://huggingface.co/mlx-community/Qwen3-ForcedAligner-0.6B-bf16/raw/53c8c0e46733eec430e4b53dd6471d0e5dee45f8/README.md)
declares Apache-2.0 and identifies conversion from
`Qwen/Qwen3-ForcedAligner-0.6B` using `mlx-audio` 0.3.1.
The full Apache License 2.0 is included in `LICENSE.Apache-2.0`.

Modification by Voices: one final newline was appended. The upstream
[configuration bytes](https://huggingface.co/mlx-community/Qwen3-ForcedAligner-0.6B-bf16/raw/53c8c0e46733eec430e4b53dd6471d0e5dee45f8/config.json)
have SHA256 `dffdf2e17fa13effca4b165540c8eeea6d3f3211dcdb6c21978e68578460858d`.
The deterministic dispatch test verifies those original bytes before use.

This developer-source fixture contains configuration only, not model weights
or executable upstream code. It is excluded from the runtime distributions
and the skills-only ZIP, but repository-root Git plugin installation fetches
the developer tree too. The Voices MIT grant does not relicense it.
