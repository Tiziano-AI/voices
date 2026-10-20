# Voice design best practices

Official Voice Design guidance is stronger than most ad hoc prompting. The local product should inherit those principles.

Primary source:

- [Alibaba Voice Design docs](https://www.alibabacloud.com/help/en/model-studio/qwen-tts-voice-design)

## Core principles

Paraphrased from the official guidance:

1. Be specific, not vague.
2. Be multidimensional, not single-axis.
3. Be objective and perceptual, not preference-only.
4. Be original, not imitative.
5. Be concise, not padded.

## Recommended description dimensions

Use these as the canonical serious-authoring checklist:

- gender or vocal identity
- age band
- pitch or register
- pace or cadence
- emotion or emotional temperature
- timbre / characteristics
- purpose / use case

The local workbench goes one step further and also tracks:

- diction / articulation
- energy
- archetype
- explicit negative constraints

## Local translation for `voices design`

For the local product:

- `--instruct` is the design description
- `--text` is the probe line

Treat `--text` as a test vector, not filler. It should expose:

- pace
- diction
- emotional shape
- whether the voice collapses into blandness or caricature

## What strong prompts tend to contain

A strong local design prompt usually combines:

- identity core: age + gender or role
- register: low, mid, high, tenor, baritone, contralto
- movement: slow, clipped, fast, deliberate, unhurried
- timbre: smoky, crisp, breathy, resonant, dry, gravelly, mellow
- emotional control: restrained, warm, playful, severe, soothing
- task fit: narration, radio host, audiobook, documentary, explainer

## What weak prompts tend to do

Weak prompts often:

- say only “nice”, “good”, or “cool”
- name just one attribute such as gender
- describe preference instead of audible traits
- rely on repetition instead of detail
- forget to say what the voice is for

## Authoring doctrine

For serious work:

- start from structured dimensions
- fill the purpose field deliberately
- add negative constraints when avoiding common failures matters
- use archetypes to sharpen a voice, but do not depend on named-person imitation

## Iteration heuristics

When a result is too generic:

- add purpose
- add one or two timbre traits
- add a pacing descriptor
- add one negative constraint such as `not theatrical`

When a result is too theatrical:

- lower the emotional temperature
- replace dramatic adjectives with restraint or control language
- add `not melodramatic` or `not stagey`

When a result is too thin or nasal:

- specify a fuller register
- add resonance or groundedness traits
- add a diction requirement

When a result is vivid but unstable:

- remove stacked adjectives that pull in different directions
- tighten to the most important 4–6 cues
