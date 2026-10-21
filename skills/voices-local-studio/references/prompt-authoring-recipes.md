# Prompt authoring recipes

For voice-creation work, start from the structured workbench spec rather than prose. Authoring a prompt does not itself run `design` or save a library voice; the generation steps below apply when creation is part of the requested outcome.

Workbench entrypoint:

- Resolve `SKILL_ROOT` to the directory containing this package's `SKILL.md`, as supplied by the host. Do not assume a global skill or plugin-cache path.
- Run `python3 "$SKILL_ROOT/scripts/voice_prompt_workbench.py"`. It uses only the Python standard library and does not need the Voices checkout or model runtime.

## Recommended authoring flow

1. `scaffold --single` or `scaffold --pack N`
2. fill the structured dimensions
3. `compose --profile balanced-literary`
4. `audit`
5. run `voices --json design --dry-run` or `voices --json design-batch --dry-run`
6. run `voices design` or `voices design-batch` only after the dry-run payload matches the intended voice ids, names, languages, prompts, and seed text

If a JSONL pack omits per-row `text`, or if you are auditing a `.txt` pack, pass shared seed text during audit so the workbench checks the same runnable contract the product enforces.

For quick ad hoc voice-creation tasks, skip the scaffold but still specify purpose, pace, timbre, energy, and one concrete negative constraint when the failure mode is obvious. Ordinary speaking tasks use a suitable saved voice instead of authoring a new one.

## Canonical prompt anatomy

A strong prompt is trait-first: identity, register, pace, energy, timbre, diction, purpose, archetype, then negative constraints.

## Pattern guidance

Replace vague labels with audible traits: register, pace, energy, diction and
use case. Add a constraint such as `not shrill`, `not theatrical` or `not salesy`
when it addresses a likely failure. Role, setting and genre can sharpen a
character, but keep the description trait-first and avoid named-person imitation.

## Seed-line design advice

Use the probe line (`text`) to surface the behavior you care about.

Good probe lines exercise long and short phrases, pauses, emphasis, consonants, and the target language. Bad probes are too short, flat, off-tone, or generic filler for a stylized voice.

## Batch-pack guidance

For packs, keep one idea per voice, separate neighboring voices by at least two dimensions, keep ids slug-safe, set non-English language explicitly, and audit before `design-batch`.

## Workbench recipes

Single voice:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL_ROOT/scripts/voice_prompt_workbench.py" scaffold --single > ./voice-spec.json
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL_ROOT/scripts/voice_prompt_workbench.py" compose ./voice-spec.json
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL_ROOT/scripts/voice_prompt_workbench.py" audit ./voice-spec.json
```

Pack:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL_ROOT/scripts/voice_prompt_workbench.py" scaffold --pack 5 > ./voice-pack.json
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL_ROOT/scripts/voice_prompt_workbench.py" compose ./voice-pack.json > ./prompts.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL_ROOT/scripts/voice_prompt_workbench.py" audit ./prompts.jsonl --default-text "Control is not the absence of feeling."
```
