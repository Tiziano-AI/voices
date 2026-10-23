# Performance identity and local admission

One performance binds the actual text, language, reference and model to its
audio. Export preserves that occurrence rather than generating a replacement.

## Reference capture and inference

`library_store.load_voice_snapshot` anchors a directory descriptor and opens
metadata, WAV and transcript descriptors with `O_NOFOLLOW` before reading any
of them. `O_NONBLOCK` prevents a FIFO from hanging before regular-file checks.
The store validates schema/id, transcript agreement and the digest of those
captured WAV bytes, then owns them in memory through runtime admission and
inference. A staged overwrite/delete either leaves the original capture usable
or fails capture before synthesis. This does not promise transactions for
arbitrary external in-place writers. HTTP reference audition returns captured
bytes too, never a validated path reopened later.

Base synthesis decodes bytes under `serialized_mlx_runtime()` through
`audio_io.read(BytesIO(...), dtype="float32", sample_rate=runtime.sample_rate,
nchannels=1)` and passes an MLX float32 array. It exhausts generation and
post-yield cleanup under the same lock.

The adopted mlx-audio 0.6.1 `_icl_cache` keys references by transcript, size
and sum: different waveforms can collide. The adapter clears this private cache
before every Base generation, retaining cached model weights. This is a narrow
upstream coupling to reassess on dependency changes, not another cache, a
model reload or a claim that an upgrade alone repairs the key.

New output drafts require `reference_text_sha256`, computed over the effective
UTF-8 transcript, alongside `reference_sha256`. Sidecars preserve both at
generation; historical missing provenance remains unknown/null, without edits.

## HTTP input contract

UI config includes `base_model_id/base_model_revision`. Voice summaries include
`reference_sha256/reference_text_sha256`. Preview clips attach an `input` object
derived from the generation draft, with:

- `voice_id`, `text`, `language`
- `base_model_id`, `base_model_revision`
- `reference_sha256`, `reference_text_sha256`

Preview and direct render accept optional `expected_reference` (both reference
digests) and `expected_model` (model id/revision). Compare accepts
`expected_references`, a map from voice id to both reference digests,
`expected_languages`, a map to each observed effective language, and the same
model expectation. The language precondition prevents a changed saved default
from silently changing a compared performance. Missing expectations request current inputs; the
bundled browser always supplies expectations. The workflow compares them with
the coherent capture/model selection before inference. Preview/render mismatches
produce HTTP 409 `InputConflictError`, not silent replacement. A valid Compare
request returns HTTP 200 with one ordered result per requested voice:
`{voice_id, clip, error}`, with exactly one of `clip` and `error` non-null.
Errors carry `error_code` and `detail`. A target mismatch is that row's
`InputConflictError`, with the same refresh instruction; other targets continue.
Malformed requests still fail as a whole before generation.

Reference-read I/O failures become `InvalidVoiceEntryError`; preview-write I/O
failures become `PreviewStorageError`. Compare reports them per target without
discarding successes. A standalone preview returns HTTP 409 or 503 respectively.
This does not recover an unseen token after process termination or a lost response.

The browser submits its exact trimmed text; the server returns its effective
normalized text. Conservative non-reuse when their normalization differs is
allowed; false reuse is not.

## Browser ownership

`useAuditionBoard` gives each performance card and attempt an opaque identity.
Freshness compares exact input fields against the latest observed library and
selection; changing a display name or ordering does not invalidate audio.
Returning to the original inputs restores freshness. **Refresh voices** observes
external changes without discarding session clips; this is not continuous
external-state monitoring.

Coverage counts distinct ready, pending, failed and unattempted targets.
Generation visits unattempted targets; failures require explicit retry. A late
response updates only its card and attempt, never recreates a removed card or
replaces a newer attempt. Playback belongs to `useAudioSession`, not generation
status.

`usePerformanceSession` owns stage preview/compare/export occurrences. Stage and
board retain original clips and successful download links across input edits.
Noncurrent clips remain playable and explicitly saveable as their original
performance, with original text and a reason they are not current. Remove/Clear
cannot discard a card while saving. Export always uses its original token;
expiration fails without replacement synthesis. No persistent browser journal
or alternate audio store is introduced.

Compare retains each successful clip and export if another target fails. Retry
requests only failed or missing current inputs, without replacing ready current
clips. A failed replacement attempt retains the previous clip as original audio
with its own effective input, not as the attempted replacement. Failures leave
successful exports linked. Removing the last library voice does not hide retained
stage/compare/board work; it disables generation without a usable target.

## Local HTTP admission

Every route requires exactly one `Host` authority: `localhost`, `127.0.0.1` or
`[::1]`, with optional ASCII decimal port 1..65535 (absent means 80), matching
the actual ASGI socket port. Mutations permit no `Origin`, or exactly one
complete `http://` authority with that same grammar and port. Userinfo, paths,
queries, fragments, controls, empty delimiters and duplicate headers fail
before effects with the existing structured error envelope.

The launcher disables proxy headers. Host/request URL and forwarded headers
are not socket authority; no remote proxy, CORS or hosted serving is added.
