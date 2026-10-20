#!/usr/bin/env python3
"""Opt-in real-model qualification; never part of the deterministic gate.

Run once with --out NEW_DIRECTORY. Existing roots are refused, including failed
runs: inspect their report/artifacts instead of replaying an uncertain effect.
No microphone, speakers, user library or default render directory is used.
"""

import argparse
import json
import os
import platform
import re
import resource
import sys
import time
import unicodedata
import wave
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from threading import Lock

import numpy as np

from voices import config
from voices.domain.create_contracts import CloneReviewRequest
from voices.util.timestamps import utc_now
from voices.workflow.clone_voice import clone_reference_voice, prepare_clone_review, transcribe_clone_audio
from voices.workflow.design_voice import create_designed_voice
from voices.workflow.synthesize_voice import render_speech

REFERENCES = {
    "Italian": (
        "Questa mattina la luce attraversa il giardino e illumina il tavolo vicino alla finestra. "
        "Parlo con calma, distinguendo ogni parola, mentre preparo una breve storia da condividere con voi."
    ),
    "English": (
        "This morning the light crosses the garden and reaches the table beside the window. "
        "I speak calmly and clearly, preparing a short story to share with everyone in the room."
    ),
}
SHORT_TEXTS = {
    "Italian": "Il piccolo laboratorio apre alle nove. Oggi proveremo una nuova idea, con attenzione e curiosità.",
    "English": "The small workshop opens at nine. Today we will try a new idea, with care and curiosity.",
}
LONG_TEXTS = {
    "Italian": (
        "All'inizio del viaggio abbiamo attraversato un paese tranquillo, dove le finestre erano ancora chiuse. "
        "Sulla piazza un fornaio sistemava il pane, mentre una bicicletta passava lentamente accanto alla fontana. "
        "Ci siamo fermati per osservare la luce sulle colline e scegliere il sentiero più semplice. "
        "Nessuno aveva fretta: la giornata offriva tempo per parlare, ascoltare e cambiare programma.\n"
        "Dopo il ponte abbiamo incontrato una donna che indicava un vecchio mulino, nascosto fra gli alberi. "
        "Il rumore dell'acqua accompagnava i nostri passi e rendeva ogni pausa piacevole. "
        "Alla fine abbiamo aperto il quaderno, scritto alcune impressioni e preparato il ritorno. "
        "Ricorderemo soprattutto quella sensazione di calma, insieme alla voglia di tornare un altro giorno."
    ),
    "English": (
        "At the beginning of our journey we crossed a quiet village, where most windows were still closed. "
        "In the square a baker arranged fresh bread while a bicycle moved slowly past the fountain. "
        "We stopped to watch the light on the hills and choose the easiest path. "
        "Nobody was in a hurry, so there was time to talk, listen, and change our plans.\n"
        "Beyond the bridge we met a woman who pointed towards an old mill hidden among the trees. "
        "The sound of water followed our footsteps and made each pause enjoyable. "
        "Finally we opened our notebook, wrote down a few impressions, and prepared to return. "
        "We will remember the peaceful morning and hope to visit again another day."
    ),
}


def normalized_words(text: str) -> list[str]:
    """Casefold Unicode words; punctuation separates words, accents are retained."""
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())


def transcript_comparison(expected: str, actual: str) -> dict[str, object]:
    """Compute word edit distance and alignment-derived edge omission signals."""
    reference, hypothesis = normalized_words(expected), normalized_words(actual)
    table = [[0] * (len(hypothesis) + 1) for _ in range(len(reference) + 1)]
    for i in range(len(reference) + 1):
        table[i][0] = i
    for j in range(len(hypothesis) + 1):
        table[0][j] = j
    for i, word in enumerate(reference, 1):
        for j, observed in enumerate(hypothesis, 1):
            table[i][j] = min(
                table[i - 1][j] + 1,
                table[i][j - 1] + 1,
                table[i - 1][j - 1] + (word != observed),
            )
    i, j = len(reference), len(hypothesis)
    operations: list[tuple[str, str]] = []
    while i or j:
        if i and j and table[i][j] == table[i - 1][j - 1] + (reference[i - 1] != hypothesis[j - 1]):
            operations.append(("match" if reference[i - 1] == hypothesis[j - 1] else "substitute", reference[i - 1]))
            i, j = i - 1, j - 1
        elif i and table[i][j] == table[i - 1][j] + 1:
            operations.append(("delete", reference[i - 1]))
            i -= 1
        else:
            operations.append(("insert", hypothesis[j - 1]))
            j -= 1
    operations.reverse()
    reference_ops = [(op, word) for op, word in operations if op != "insert"]
    leading: list[str] = []
    trailing: list[str] = []
    for op, word in reference_ops:
        if op != "delete":
            break
        leading.append(word)
    for op, word in reversed(reference_ops):
        if op != "delete":
            break
        trailing.append(word)
    return {
        "normalization": "Unicode NFKC, casefold, punctuation-separated words; accents retained",
        "reference_words": len(reference),
        "hypothesis_words": len(hypothesis),
        "word_error_rate": table[-1][-1] / len(reference) if reference else None,
        "word_edit_distance": table[-1][-1],
        "substitutions": sum(op == "substitute" for op, _ in operations),
        "deletions": sum(op == "delete" for op, _ in operations),
        "insertions": sum(op == "insert" for op, _ in operations),
        "leading_reference_omissions": leading,
        "trailing_reference_omissions": list(reversed(trailing)),
        "first_expected_words": reference[:8],
        "first_asr_words": hypothesis[:8],
        "last_expected_words": reference[-8:],
        "last_asr_words": hypothesis[-8:],
        "limit": "ASR disagreement and alignment signals, not proof of spoken omissions or listening acceptance",
    }


def audio_metrics(path: Path) -> dict[str, object]:
    """Measure the actual published PCM, not an unpersisted generation array."""
    with wave.open(str(path), "rb") as audio:
        if audio.getsampwidth() != 2 or audio.getnchannels() != 1:
            raise ValueError("Expected canonical mono PCM16 WAV")
        sample_rate = audio.getframerate()
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(np.float64)
    if samples.size == 0:
        raise ValueError("Published audio contains no samples")
    normalized = samples / 32767.0
    return {
        "sample_rate": sample_rate,
        "samples": int(samples.size),
        "duration_seconds": float(samples.size / sample_rate),
        "peak_amplitude": float(np.max(np.abs(normalized))),
        "rms_amplitude": float(np.sqrt(np.mean(normalized * normalized))),
        "clipping_fraction": float(np.mean(np.abs(samples) >= 32767)),
        "measurement_source": "published PCM16 WAV; clipping is full-scale sample fraction, not pre-encode overshoot",
    }


class Qualification:
    """Single-use isolated run with durable event checkpoints before effects."""

    def __init__(self, out: Path) -> None:
        if out.expanduser().exists() or out.expanduser().is_symlink():
            raise FileExistsError(out)
        self.out = out.expanduser().resolve()
        protected = (config.get_library_path().resolve(), config.DEFAULT_OUTPUT_DIR.resolve())
        if any(self.out == root or root in self.out.parents for root in protected):
            raise ValueError("--out must be outside the user voice library and default render root")
        self.out.mkdir(parents=True, exist_ok=False)
        self.library = self.out / "library"
        self.library.mkdir()
        self.events: list[dict[str, object]] = []
        self.lock = Lock()
        self.record(
            "run",
            "started",
            python=sys.version,
            platform=platform.platform(),
            packages={name: version(name) for name in ("mlx-audio", "mlx", "transformers")},
            models={"design": config.VOICE_DESIGN_MODEL, "base": config.BASE_MODEL, "stt": config.STT_MODEL},
            library=str(self.library),
            listening_acceptance="not performed",
            clone_policy="synthetic non-person voice; machine comparison only, no human approval",
            recovery="Never rerun in this root. Inspect events and retained artifacts after interruption.",
        )

    def record(self, case: str, state: str, **details: object) -> None:
        """Append and fsync each event before replacing the current JSON projection."""
        with self.lock:
            event: dict[str, object] = {"case": case, "state": state, "at": utc_now(), **details}
            with (self.out / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self.events.append(event)
            temporary = self.out / ".report.json.tmp"
            temporary.write_text(
                json.dumps({"events": self.events}, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            )
            temporary.replace(self.out / "report.json")
            print(f"{case}: {state}", flush=True)

    @contextmanager
    def step(self, case: str, **details: object) -> Iterator[None]:
        """Record failure without retrying or deleting partially published artifacts."""
        self.record(case, "started", **details)
        start = time.monotonic()
        try:
            yield
        except BaseException as error:
            self.record(
                case,
                "failed",
                error_type=type(error).__name__,
                error=str(error),
                elapsed_seconds=time.monotonic() - start,
            )
            raise
        self.record(case, "completed", elapsed_seconds=time.monotonic() - start)

    def measure(self, case: str, path: Path, expected: str, language: str) -> None:
        """Persist metrics before independent audio-only ASR so ASR failure loses neither."""
        self.record(case, "audio_measured", wav=str(path), **audio_metrics(path))
        with self.step(case + ":asr", wav=str(path), language=language):
            draft = transcribe_clone_audio(audio_path=path, language=language)
            self.record(
                case,
                "transcribed",
                input=expected,
                transcription=draft.model_dump(mode="json"),
                comparison=transcript_comparison(expected, draft.transcript),
            )

    def design(self, language: str) -> str:
        voice_id = "design-" + language.lower()
        reference = self.library / voice_id / "reference.wav"
        instruct = f"A fictional adult narrator speaking {language}, warm, clear, natural and conversational."
        with self.step(
            voice_id,
            input=REFERENCES[language],
            language=language,
            instruct=instruct,
            expected_voice_directory=str(reference.parent),
        ):
            start = time.monotonic()
            record = create_designed_voice(
                voice_id=voice_id,
                name=f"Qualification {language}",
                instruct=instruct,
                text=REFERENCES[language],
                language=language,
                library=self.library,
                overwrite=False,
            )
            self.record(
                voice_id,
                "voice_persisted",
                voice=record.model_dump(mode="json"),
                wav=str(reference),
                generation_and_save_seconds=time.monotonic() - start,
            )
            self.measure(voice_id, reference, REFERENCES[language], language)
        return voice_id

    def clone(self) -> str:
        source = self.library / "design-english" / "reference.wav"
        voice_id = "clone-english"
        with self.step("clone-review", source=str(source), source_is_synthetic=True, human_approval=False):
            prepared = prepare_clone_review(
                audio_path=source,
                library=self.library,
                request=CloneReviewRequest(language="English", fallback_name=voice_id),
            )
            self.record(
                "clone-review",
                "review_retained",
                draft=prepared.draft.model_dump(mode="json"),
                comparison=transcript_comparison(REFERENCES["English"], prepared.draft.transcript),
            )
        with self.step(
            "clone-save",
            machine_test_only=True,
            human_approval=False,
            expected_voice_directory=str(self.library / voice_id),
        ):
            record = clone_reference_voice(
                voice_id=voice_id,
                name="Synthetic qualification clone",
                audio_path=source,
                transcript=prepared.draft.transcript,
                language="English",
                library=self.library,
                overwrite=False,
            )
            self.record("clone-save", "voice_persisted", voice=record.model_dump(mode="json"))
        return voice_id

    def render(self, case: str, voice_id: str, text: str, language: str) -> None:
        destination = self.out / "renders" / case
        with self.step(case, voice_id=voice_id, input=text, language=language, output_directory=str(destination)):
            start = time.monotonic()
            wav = render_speech(
                voice_id=voice_id, text=text, language=language, library=self.library, out_dir=destination
            )
            self.record(
                case,
                "audio_persisted",
                wav=str(wav),
                sidecar=str(wav.with_suffix(".json")),
                generation_and_save_seconds=time.monotonic() - start,
            )
            self.measure(case, wav, text, language)

    def run(self, parallel: bool) -> None:
        """Generate sequentially first; optional paired callers still use product locking."""
        for language in REFERENCES:
            self.design(language)
        clone_id = self.clone()
        for language in REFERENCES:
            voice_id = "design-" + language.lower()
            self.render(language + "-short", voice_id, SHORT_TEXTS[language], language)
            self.render(language + "-long", voice_id, LONG_TEXTS[language], language)
            for repeat in range(1, 3):
                self.render(f"{language}-repeat-{repeat}", voice_id, SHORT_TEXTS[language], language)
        self.render("clone-short", clone_id, SHORT_TEXTS["English"], "English")
        if parallel:
            # Wait for both owned operations to settle even if one raises. Do not
            # claim cancellation of model generation or leave a worker unmanaged.
            errors: list[BaseException] = []
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(
                        self.render,
                        "parallel-" + language,
                        "design-" + language.lower(),
                        SHORT_TEXTS[language],
                        language,
                    )
                    for language in REFERENCES
                ]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except BaseException as error:
                        errors.append(error)
            if errors:
                raise errors[0]
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        self.record(
            "run",
            "measurements_completed",
            listening_acceptance="not performed",
            process_peak_rss_bytes=peak if sys.platform == "darwin" else peak * 1024,
            quality_verdict="Requires interpretation of ASR measures and direct listening; no automatic pass",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, required=True, help="New isolated run directory; existing paths are refused"
    )
    parser.add_argument(
        "--parallel", action="store_true", help="Also exercise two concurrent callers after sequential runs"
    )
    arguments = parser.parse_args()
    try:
        run = Qualification(arguments.out)
    except FileExistsError:
        parser.error("--out already exists; inspect its retained report instead of replaying this run")
    try:
        run.run(arguments.parallel)
    except BaseException as error:
        run.record(
            "run",
            "aborted",
            error_type=type(error).__name__,
            error=str(error),
            retained_root=str(run.out),
            recovery="Inspect retained artifacts; no automatic regeneration",
        )
        if isinstance(error, KeyboardInterrupt):
            return 130
        raise
    print(f"Measurements: {run.out / 'report.json'}; listening acceptance remains unperformed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
