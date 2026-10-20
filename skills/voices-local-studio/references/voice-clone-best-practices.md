# Voice clone best practices

Primary source:

- [Alibaba voice cloning docs](https://www.alibabacloud.com/help/en/model-studio/qwen-tts-voice-cloning)

## Source-audio requirements

Use these as the local preparation checklist:

- supported source formats: any local file that the installed `ffmpeg` can decode
- preferred duration: enough clean speech to represent the target voice without forcing the operator through avoidable noise
- product duration limits: free recording enforces the repo minimum before transcript review; imported clone files do not have a separate extension or duration allowlist
- sample rate: at least 24 kHz
- clear speech segment: at least 3 seconds of continuous clear speech
- no background music
- no background noise
- no overlapping speakers
- no singing

## Transcript quality

Treat transcript accuracy as part of the clone quality budget.

Use a transcript that is:

- exact or near-exact
- in the same language as the source clip
- cleaned of obvious punctuation noise only when it improves alignment
- not paraphrased

If the transcript is materially wrong, the clone path becomes less reliable even when the audio is good.

## Reject or quarantine weak reference clips

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

That means the clone path depends on both:

- acoustic cleanliness
- transcript fidelity

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

Prefer `design` when:

- you want a reusable synthetic character voice
- you need consistency across many lines
- you want the designed persona to become the saved reusable reference immediately without a second clone step
