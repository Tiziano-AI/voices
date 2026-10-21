# Upstream capability matrix

This skill is local-product-first. Use this matrix to avoid conflation.

| Surface | What it is | Canonical for this skill? | Relevant distinction |
| --- | --- | --- | --- |
| Local `voices` product | Single installed CLI, resolved with `command -v voices` | Yes | Doctor identifies the selected runtime; other projects must not supply private Voices environments or caches. |
| Local `mlx-audio` runtime | The installed MLX Qwen implementation behind the repo | Yes, as runtime evidence | Proves what the local product can actually call. |
| Official Qwen open-source docs/examples | Upstream Qwen README and examples | No | Useful for capabilities, patterns, and terminology comparison. |
| Hosted Alibaba Model Studio docs | Hosted API docs for Voice Design, voice clone, and instruction control | No | Useful for best practices and hosted-only distinctions, not as local product truth. |

## Term mapping

| Term | Local `voices` meaning | Upstream/hosted note |
| --- | --- | --- |
| `--instruct` | VoiceDesign description used by the local `design` command | Not the same thing as hosted synthesis `instructions`. |
| `instruction` / `instructions` | Not a local public surface | Hosted Qwen synthesis docs use this for expressive control on supported instruct models. |
| `voice_prompt` | Not a local CLI flag | Hosted Alibaba Voice Design uses this for the design description field. |
| `preview_text` | Not a local CLI flag | Hosted Voice Design uses a preview line to audition the designed voice. Local `voices design --text` plays the same practical role. |
| `ref_audio` | Clone conditioning audio | Local product stores this as `reference.wav`. |
| `ref_text` | Transcript for the reference audio | Local product stores this as `reference.txt`. |

## Local runtime vs official Qwen examples

Official Qwen examples include helpers the local product intentionally does not expose:

- `design` uses a VoiceDesign-style generation path
- `clone`, `say`, and `render` reuse saved reference assets through the Base model path

Use upstream examples for patterns, not as proof of local API.

## Hosted guidance that matters but is not local contract

- Hosted Voice Design docs define strong writing principles for `voice_prompt`.
- Hosted voice-cloning docs define audio quality requirements.
- Hosted synthesis docs describe model-specific instruction controls and language limits; they do not add a local synthesis flag.

These are references, not local product rules.

## Stable distinctions agents must preserve

- Local operation follows the installed CLI and its observed runtime; canonical source docs explain its contract.
- Upstream open-source Qwen docs are best-practice and capability references.
- Hosted Alibaba docs may be stricter or broader than the local product.
- Never tell the user that a hosted-only surface or restriction is automatically available locally unless the repo or runtime proves it.

Primary sources:

- [Qwen3-TTS GitHub README](https://github.com/QwenLM/Qwen3-TTS)
- [Alibaba Voice Design docs](https://www.alibabacloud.com/help/en/model-studio/voice-design-user-guide)
- [Alibaba voice cloning docs](https://www.alibabacloud.com/help/en/model-studio/voice-cloning-user-guide)
- [Alibaba speech synthesis docs](https://www.alibabacloud.com/help/en/model-studio/non-realtime-tts-user-guide)
