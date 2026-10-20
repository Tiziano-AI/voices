# Record and clone workflow

## Product law

- `record` is the easiest ingress into the clone workflow
- a successful record flow ends with a saved clone voice in the library
- imported audio and recorded audio converge on the same persisted clone contract
- imported clone work is two-phase: `clone review` creates the durable review handoff, and `clone save` persists the approved voice
- `record plan` is the non-interactive way to inspect scripts, timing, and stop rules before microphone capture
- only the operator-approved transcript becomes the final saved transcript

## Guided vs free

Use `guided` record when:

- the operator wants the easiest success path
- a curated script is acceptable
- automatic stop after the target window is helpful

Use `free` record when:

- the operator wants to improvise or speak naturally
- the clip does not fit a fixed script
- manual stop is part of the desired capture flow

## Transcript review doctrine

For both imported and recorded clone flows:

- expose take playback before transcript approval
- show the actual STT transcript
- let the operator accept, retry, edit, or replay the take
- do not silently save a bad transcript
- treat a transcript draft and a final saved transcript as different states
- do not hide saving behind a broad import step in JSON-driven clone work
- in the browser, a failed transcript review retains the captured take for explicit retry or download; do not ask the operator to record again unless they choose to reset
- resetting or closing the recording panel discards an unsaved take; download it first when the operator wants to keep it

## Review-step law

- CLI review must expose playback as an explicit action, not as an off-path workaround
- UI review must frame playback as a visible review step, not as an unlabeled audio control
- if playback is unavailable, treat transcript approval as degraded and say so explicitly

## Language doctrine

- language choice happens before transcription and save
- keep the public product surface aligned with the supported Voices language set
- do not widen public product language scope just because the STT runtime can do more
