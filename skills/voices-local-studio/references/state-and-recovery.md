# State and recovery

## Check the selected installation
- Resolve the installed `voices` command and inspect doctor identity first; source docs explain behavior but do not prove the selected installation.
- Use the standard shared model cache with immutable revisions. If installation/cache selection differs from the canonical contract, report the discrepancy; do not provision a private source/Python/venv, duplicate cache or fallback.

## Studio lifecycle

- The bundled browser UI is launched by `voices ui` for one selected library and loopback host/port.
- `--host` accepts only `127.0.0.1`, `localhost`, or `::1`.
- `--port` selects the listening port for the current process.
- The product has no `voices ui status`, `voices ui stop`, runtime lock file, or `/api/health` contract.

## Runtime-state contract

- `voices doctor` checks readiness without loading a model.
- Runtime UI state is process-owned by the terminal session running `voices ui`.
- Unsaved browser previews and compare clips are temporary, cleaned up when the edge stops. **Save preview**, board **Save clip**, **Save original clip** and **Save compared clips** retain those exact WAV bytes and generation-time provenance. A token exports once; retry reuses its persisted pair. An expired token fails without generating replacement audio. Partial compare saves retain successful downloads.
- A partial comparison retains playable/saveable successes; **Retry** requests only failed current inputs. A failed replacement keeps the earlier clip and its download, never presenting it as the replacement. Removing the last library voice leaves retained stage/compare/board work accessible, but new generation needs an available voice.
- A board card is one performance, not a voice slot. Freshness compares exact text, effective language, reference WAV/transcript and model against the latest observed inputs. Input edits retain old clips and links; returning to the same inputs restores freshness. **Save original clip** explicitly saves noncurrent audio. Remove/Clear wait for its save to finish. Coverage separates distinct ready, pending, failed and unattempted voices; retry failed cards explicitly.
- If generation reports changed reference/model inputs, refresh before retrying. The server rejects a mismatched selection before inference rather than silently using the replacement reference.
- An unreviewed browser recording stays in the open recording panel. If transcript review fails, retry the same take or download its bytes without recording again. Closing or resetting discards the unsaved take. This is not crash recovery.
- Closing or resetting during microphone permission retires any stream granted afterward; it cannot dismiss the browser or operating-system permission prompt.
- Saved voices and rendered outputs remain in `~/.voices` and `./outputs`.

## Recover the work

- If `voices ui` reports a port conflict, choose a free loopback port or stop the terminal process that owns the port.
- If the browser bundle is missing, report the selected installation and route repair to repository materialization guidance; do not start a second implementation.
- If the library blocker appears, inspect the saved library before retrying UI launch.
- When cleanup is necessary, stop the terminal process that launched `voices ui`.
