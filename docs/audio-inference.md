# Existing-audio inference

Both commands use the canonical installed CLI, standard shared Hugging Face
cache and existing serialized MLX runtime. They leave source files untouched,
start neither capture nor playback, and need intent for model inference and
any missing-snapshot download. No voice, clone candidate, review handoff,
audio output or transcript file is saved.

## Audio-only transcription

Recognize words from an existing WAV without supplying the expected transcript:

```bash
voices --json transcribe --audio ./speech.wav --language English \
  --model-revision e1f6c266914abc5a46e8756e02580f834a6cf8a7
```

All three options are required. Use public language names such as `English` or
`Italian` (case-insensitive), not ISO codes. The model is
`mlx-community/Qwen3-ASR-1.7B-bf16`; the revision must be a full immutable
40-hex commit SHA. `doctor` exposes its configured identity as `models.stt` and
`model_revisions.stt`. Human mode prints the transcript.

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
adjustment diagnostics exist. Japanese needs `nagisa`, Korean `soynlp`; absent
tokenizers fail with `missing_dependency` before model loading.

## Failures and interpretation

Both commands emit the standard `error.code/message/exit_code` envelope in
global `--json` mode; stdout contains exactly one JSON document. Invalid input
fails before model loading; malformed inference results are `generation`
errors. Missing local dependencies report `missing_dependency`; undecodable or
empty audio reports `audio_conversion`. A failed command has no library or
output mutation to reconcile; a model snapshot may have entered the shared
cache. Retrying after correcting the reported input/setup does not replay an
application effect or overwrite the source.
