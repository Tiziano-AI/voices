# Voice clone best practices

## Prepare the reference

Use only a recording the operator has permission to clone. Choose one speaker
with clear, natural speech, little reverberation and no music or overlapping
voices. Avoid singing or a delivery so extreme that it would be unwanted in
later lines. Listen before spending effort on the transcript.

Voices imports local formats the installed FFmpeg can decode. Imported files
have no separate extension or duration allowlist; free recording enforces its
minimum before transcript review. Use `record plan` to inspect that minimum.

Clean source quality matters more than meeting a hosted service's numeric
limits. [Alibaba's recording guidance](https://www.alibabacloud.com/help/en/model-studio/voice-cloning-user-guide)
offers useful preparation advice, but its upload, duration and sample-rate
requirements belong to that hosted API, not this local product. Prefer an
original recording over an upsampled or heavily compressed copy.

## Transcript quality

Use a transcript that is:

- faithful to the words actually spoken
- in the same language as the source clip
- cleaned of obvious punctuation noise only when it improves alignment
- not paraphrased

If the transcript is materially wrong, the clone path becomes less reliable even when the audio is good.

## Replace weak reference clips

Advise against cloning when the clip is:

- too short
- noisy
- reverberant or distant
- mixed with other speakers
- compressed badly
- spoken over music
- emotionally extreme in a way the user does not want baked into the reference

## Local product translation

In the local product:

- `voices clone review` imports the clip through `ffmpeg` and writes a review JSON plus normalized WAV
- `voices clone save` persists the operator-approved review as a saved clone voice
- the cleaned reference becomes `reference.wav`
- the transcript becomes `reference.txt`

Check the draft against the normalized WAV and correct its `transcript` field
before `clone save`. Saving does not add a second transcript-approval prompt.

## Design vs clone decision rule

Choose between these paths when creating a new reusable voice is in scope. For ordinary speech, select a suitable saved voice; source-audio or style fit alone does not authorize library creation.

Prefer `design` when:

- the target is fictional or persona-driven
- there is no clean source speaker
- you need many stylized variants quickly

Prefer `clone` when:

- there is a real reference speaker
- the source audio is clean
- speaker identity matters more than invented style

`design` saves the synthetic reference directly; it needs no second clone step.
