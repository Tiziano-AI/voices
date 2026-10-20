# Troubleshooting and evaluation

## Evaluate output on audible dimensions

Listen for:

- register and weight
- pace and pause behavior
- diction and consonant clarity
- emotional temperature
- timbre stability
- fit for purpose

## Common failures

### Too generic

Likely causes:

- prompt is single-axis
- no purpose
- weak probe line

Try:

- add purpose
- add two stronger timbre traits
- add one negative constraint

### Too theatrical

Likely causes:

- stacked dramatic adjectives
- archetype dominates the trait bundle

Try:

- lower emotional intensity
- replace drama words with restraint words
- add `not theatrical`, `not stagey`, or `not melodramatic`

### Too breathy or thin

Likely causes:

- under-specified register
- too much softness, too little structure

Try:

- specify low or mid register
- add groundedness, resonance, or cleaner diction

### Clone sounds poor

Likely causes:

- noisy or distant source clip
- transcript mismatch
- unstable language conditions

Try:

- replace the source clip
- fix the transcript
- use a cleaner segment

### Wrong language feel

Likely causes:

- unsupported or mismatched language label
- probe line is not in the target language
- clone transcript and desired synthesis language do not align well

Try:

- keep the product language explicit
- use a language-matched probe line
- verify the clone transcript

## Iteration discipline

When tuning a prompt:

- change one variable at a time
- keep the probe line stable while changing the design prompt
- if the voice family is wrong, rewrite the prompt instead of nudging endlessly

## Audit before trust

Before adopting a prompt pack as reusable guidance:

- run the workbench audit
- check for vague or single-axis prompts
- check for imitation-risk language
- check for missing purpose and weak ids
