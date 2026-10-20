# STT capability and language contract

## Local runtime posture

- the local product uses MLX-native STT capability rather than a hosted transcription dependency
- STT assists clone and record review and recognizes existing WAVs through public `transcribe`; it uses the same ASR adapter and shared runtime

## Product contract

- the operator chooses language explicitly for record, clone-assist and audio-only transcription
- the product language surface stays aligned with the supported Voices creation and synthesis languages
- transcript assistance improves the workflow but does not override operator approval
- playback review remains independent from STT quality and must stay available before final approval

## Supplied-text alignment is separate

`voices --json align` estimates where supplied words fall in existing audio.
It does not recognize words independently and always reports
`spoken_content_verified=false`. Estimator-adjusted word timing (including
zero-width words) and absent raw correction diagnostics cannot prove omissions,
phonetic accuracy or constant pace. Use audio-only ASR for a separate transcript
comparison and listening for human quality acceptance. Public
`voices --json transcribe` provides that audio-only recognition with an explicit
immutable model revision and original/normalized audio identity. It creates no
voice, clone candidate or review file, and accepts no expected transcript.

## Practical guidance

- use STT to reduce friction when the user lacks a ready transcript
- preserve manual correction and retry as first-class recovery paths
- explain broader upstream STT capability only when it materially affects the current product task
