# Existing-audio inference

Audio-only transcription and supplied-text alignment leave source files untouched
and start neither capture nor playback. They save no voice, clone candidate,
review handoff, audio output or transcript file. The default MLX path uses the
standard shared Hugging Face cache and serialized MLX runtime; a missing pinned
snapshot needs download authority. Explicit DGX uses retained checkpoints with
no download or fallback, as described below.

## Optional DGX compute

Select it explicitly for one CLI invocation or studio session; omission stays
MLX. The DGX needs the retained cached CUDA image, two audio overlays and pinned
checkpoints, plus a vacant lane admitted by its operator. Voices neither
downloads/provisions that foundation nor stops an existing workload. Existing
SSH authorization and strict known-host verification are required; no speech
listener, pairing or new credentials are created.

```bash
voices --compute dgx --dgx-host <existing-alias> --dgx-ssh-config <existing-config> \
  --json doctor --library <local-library>
voices --compute dgx --dgx-host <existing-alias> --dgx-ssh-config <existing-config> \
  ui --library <local-library> --no-open
```

The studio displays its effective backend. VoiceDesign, Base, audio-only STT
and supplied-text alignment share this selection; reference review, library,
capture, normalization, playback and exact-preview export stay on Mac. Doctor's
`compute.models` owns the selected DGX model/revision catalogue; its local
`runtime` is not remote readiness or CUDA provenance. Generated sidecars carry
the actual remote checkpoint, worker source, controls and CUDA identity.

An interrupted SSH call names its retained invocation and private custody root
(`--compute-state` can select an isolated root). Use the same SSH selection with
`--json compute inspect <invocation>` or `--json compute collect <invocation>`.
Collection can naturally settle the exact invocation-owned child after a dead
owner's cleanup failure. It refuses live or ambiguous ownership; existing local
collection bytes must match the fetched receipt. These commands never resubmit,
fall back to MLX, save a voice or publish an
output. Cancellation can suppress publication without interrupting accepted
GPU work. Inspect/settle the original invocation before further work; an
unknown outcome is not permission to generate again. No streaming guarantee
or audible quality acceptance follows from a complete result.

### Remote execution and input contract

Base receives captured reference WAV bytes and the approved transcript with
independent hashes. ASR receives normalized audio and language, not expected
text. Alignment receives separately supplied text and keeps non-verification.
DGX uses retained offline overlays/checkpoints, never the MLX-dependent wheel.
`voices_version` is the submitting product version, not an installed DGX wheel;
worker-source scope and actual Torch/CUDA/image identity remain explicit.

## Capture and review

After any non-design ingress produces an audio file, both the CLI and the browser studio must call the same post-capture review owner: `voices.workflow.clone_voice`.

- `review_policy="import"` covers imported clone audio and does not enforce an extra minimum duration
- `review_policy="record_guided"` covers guided recording and reuses the same transcript-review and save path without an extra minimum
- `review_policy="record_free"` covers free recording and enforces the product minimum before transcript review is allowed
- the only legal persistence step after review is `clone_reference_voice`, so `record` and `clone` save the same persisted voice kind
- browser review tokens are single-spend. The save path claims one token exclusively before persistence, releases that claim only when persistence fails, and retires the token plus temp audio immediately after one successful save so concurrent saves cannot duplicate one approved take

## Audio-only transcription

Recognize words from an existing WAV without supplying the expected transcript:

```bash
voices --json transcribe --audio ./speech.wav --language English \
  --model-revision e1f6c266914abc5a46e8756e02580f834a6cf8a7
```

All three options are required. Use public language names such as `English` or
`Italian` (case-insensitive), not ISO codes. The model is
`mlx-community/Qwen3-ASR-1.7B-bf16` for MLX; the revision must be a full immutable
40-hex commit SHA. `doctor` exposes its configured identity as `models.stt` and
`model_revisions.stt`. Human mode prints the transcript.
For DGX use the selected `compute.models.asr` revision from doctor, not the
MLX revision. Remote generation records worker-source/CUDA identity, not the
client's MLX runtime; no supplied transcript is sent to ASR.

JSON returns `transcript`, normalized `language`, `model_id`, `model_revision`,
`runtime` and `audio`. The audio object contains the absolute original `path`
and `sha256`, plus `normalized_sha256`, `normalized_dtype="<f4"`, `channels=1`,
`sample_rate=16000`, `duration_seconds`, and
`waveform_basis="ffmpeg-normalized-mono-pcm16-to-float32"`. Runtime identity is
observed before inference, using the same contract as doctor, render and align.

The actual WAV container is checked before normalization; the extension alone
does not establish its type. FFmpeg normalizes in memory, and the original
file hash is checked again before inference. Changed source bytes fail closed.
The existing `mlx_stt` adapter owns pinned snapshot loading, ASR generation and
runtime cache under `serialized_mlx_runtime()`; no parallel ASR API or private
runtime is introduced.

An ASR transcript is independent recognition evidence, not a verdict on
pronunciation, delivery or listening quality. No supplied-text alignment or
segment-timing claim accompanies it.

## Supplied-text alignment

Estimate where supplied UTF-8 words fall in existing audio:

```bash
voices --json align --audio ./speech.wav --text-file ./line.txt \
  --language English \
  --model-revision 53c8c0e46733eec430e4b53dd6471d0e5dee45f8
```

This uses `mlx-community/Qwen3-ForcedAligner-0.6B-bf16`, not ASR. Unlike
`transcribe`, the exact revision is optional and defaults to the configured
immutable aligner revision. JSON contains model/runtime identity, the same
original and normalized `audio` identity as transcription, exact supplied
`text`, public `language`, and `words` with `text`, `start`, `end` in seconds.

`spoken_content_verified=false`: supplied-text alignment does not prove those
words were spoken. `timing_basis="qwen-forced-aligner-estimator-adjusted"` and
`timing_diagnostics=null` remain explicit. Zero-width words are allowed; no raw
adjustment diagnostics exist. On MLX, Japanese needs `nagisa` and Korean
`soynlp`; absent local tokenizers fail before model loading. Explicit DGX
selection leaves tokenizer dependencies with its remote runtime, not the Mac.

## Failures and interpretation

Both commands emit the standard `error.code/message/exit_code` envelope in
global `--json` mode; stdout contains exactly one JSON document. Invalid input
fails before model loading; malformed inference results are `generation`
errors. Missing local dependencies report `missing_dependency`; undecodable or
empty audio reports `audio_conversion`. A failed command has no library or
output mutation to reconcile; a model snapshot may have entered the shared
cache. Retrying after correcting the reported input/setup does not replay an
application effect or overwrite the source on the local path. An uncertain DGX
transport instead requires same-invocation inspect/collect before any new work;
it is never automatically replayed, even for read-only ASR/alignment.
