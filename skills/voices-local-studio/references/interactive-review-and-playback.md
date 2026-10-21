# Interactive review and playback

Listen to the recorded or imported take before accepting its transcript and
saving it as a reusable voice. Recognition can help draft a transcript, but
cannot establish how the reference sounds.

## Terminal review

For interactive CLI review:

1. play the recorded or imported take on demand during transcript review
2. keep transcript approval and playback in the same loop
3. never require the operator to leave the command just to hear the take

## Studio review

For bundled UI review:

1. show playback as an explicit review step
2. keep the audio control adjacent to the transcript review surface
3. tell the operator to listen before approving the transcript or saving the voice

## Agent-harness recipe

When the agent is driving `voices record` through an interactive harness:

1. ask the operator for the language first
2. show the exact guided script for that language
3. state the precise guided duration or the free-mode stop rule
4. start the record command only after the operator confirms readiness
5. after capture, call out the playback option before asking for transcript approval

## When review fails

- if STT is weak but playback is good, the operator may still edit the transcript confidently
- if playback is poor, prefer retry over transcript polishing
- if playback itself is unavailable, surface that as a degraded review path instead of pretending approval is normal
