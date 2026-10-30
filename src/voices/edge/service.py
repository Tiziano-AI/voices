import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from fastapi import UploadFile

from voices import config
from voices.cli_support import default_display_name
from voices.compute import LOCAL_COMPUTE, ComputeSelection
from voices.domain.contracts import DesignPromptInput, OutputRecord, VoiceRecord
from voices.domain.create_contracts import CloneReviewRequest
from voices.domain.errors import InvalidInputError, InvalidPromptFileError, VoicesError
from voices.domain.speech_contracts import SpeechInput
from voices.edge.contracts import (
    BatchDesignForm,
    BatchDesignResult,
    BatchDesignRow,
    CloneReviewDraft,
    CloneReviewForm,
    CloneSaveRequest,
    CompareFailure,
    CompareRequest,
    CompareResult,
    CompareSuccess,
    DesignRequest,
    PreviewClip,
    PreviewRequest,
    RenderArtifact,
    RenderRequest,
    VoiceDetail,
    VoiceSummary,
)
from voices.edge.errors import edge_payload_for_error
from voices.edge.storage import StudioAssetStore
from voices.store.library_store import delete_voice_record as delete_persisted_voice
from voices.store.library_store import list_voice_records, load_voice_record, load_voice_snapshot
from voices.util.prompt_loader import load_prompts
from voices.workflow.clone_voice import clone_reference_voice, prepare_clone_review, suggest_voice_id
from voices.workflow.design_voice import (
    PreparedDesignedVoice,
    prepare_designed_voice,
    save_prepared_designed_voice,
)
from voices.workflow.synthesize_voice import prepare_speech, render_speech


class OperationCancellationRegistry:
    """Thread-safe cancellation tokens for browser-owned mutating operations."""

    def __init__(self) -> None:
        """Create an empty cancellation registry."""
        self._lock = Lock()
        self._tokens: set[str] = set()

    def cancel(self, token: str) -> None:
        """Mark one operation token as canceled."""
        with self._lock:
            self._tokens.add(token)

    def is_cancelled(self, token: str | None) -> bool:
        """Return whether one operation token is currently canceled."""
        if token is None:
            return False
        with self._lock:
            return token in self._tokens

    def forget(self, token: str | None) -> None:
        """Remove one operation token after the request reaches a terminal state."""
        if token is None:
            return
        with self._lock:
            self._tokens.discard(token)


@dataclass(frozen=True, slots=True)
class StudioContext:
    """Resolved process-local configuration for one edge app."""

    library: Path
    out_dir: Path
    asset_store: StudioAssetStore
    cancellations: OperationCancellationRegistry = field(default_factory=OperationCancellationRegistry)
    compute: ComputeSelection = LOCAL_COMPUTE


@dataclass(frozen=True, slots=True)
class LoadedBatchDesign:
    """Prompt-pack rows and form defaults ready for browser batch processing."""

    prompts: list[DesignPromptInput]
    form: BatchDesignForm


def summary_from_record(record: VoiceRecord) -> VoiceSummary:
    """Project one persisted voice into the rack summary contract."""
    return VoiceSummary(
        id=record.id,
        name=record.name,
        language=record.language,
        source_kind=record.source_kind(),
        description=record.description(),
        created_at=record.created_at,
        reference_sha256=record.reference_sha256,
        reference_text_sha256=record.reference_text_sha256,
    )


def detail_from_record(record: VoiceRecord) -> VoiceDetail:
    """Project one persisted voice into the inspector detail contract."""
    return VoiceDetail(
        summary=summary_from_record(record),
        record=record,
        reference_text=record.reference_text,
        reference_audio_url=f"/api/voices/{record.id}/reference-audio",
    )


def list_voice_summaries(library: Path) -> list[VoiceSummary]:
    """Return the full playable rack projection."""
    return [summary_from_record(record) for record in list_voice_records(library)]


def load_voice_detail(library: Path, voice_id: str) -> VoiceDetail:
    """Return one inspector detail payload."""
    return detail_from_record(load_voice_record(library, voice_id))


def create_preview_clip(
    context: StudioContext, request: PreviewRequest, *, expected_language: str | None = None
) -> PreviewClip:
    """Generate one ephemeral preview clip."""
    generated = prepare_speech(
        voice_id=request.voice_id,
        text=request.text,
        language=request.language,
        library=context.library,
        expected_reference=request.expected_reference,
        expected_model=request.expected_model,
        expected_language=expected_language,
        compute=context.compute,
    )
    asset = context.asset_store.save_preview_audio(generated.audio, generated.sample_rate, generated.output_draft)
    return PreviewClip(
        token=asset.token,
        voice_id=generated.voice.id,
        kind="generated",
        language=generated.output_draft.language,
        audio_url=f"/api/assets/{asset.token}.wav",
        input=SpeechInput(
            voice_id=generated.output_draft.voice_id,
            text=generated.output_draft.text,
            language=generated.output_draft.language,
            base_model_id=generated.output_draft.base_model_id,
            base_model_revision=generated.output_draft.base_model_revision,
            reference_sha256=generated.output_draft.reference_sha256,
            reference_text_sha256=generated.output_draft.reference_text_sha256,
        ),
    )


def create_compare_clips(context: StudioContext, request: CompareRequest) -> list[CompareResult]:
    """Return every target's outcome without losing earlier successful previews."""
    results: list[CompareResult] = []
    for voice_id in request.voice_ids:
        try:
            clip = create_preview_clip(
                context,
                PreviewRequest(
                    voice_id=voice_id,
                    text=request.text,
                    language=request.language,
                    expected_reference=(request.expected_references or {}).get(voice_id),
                    expected_model=request.expected_model,
                ),
                expected_language=(request.expected_languages or {}).get(voice_id),
            )
            results.append(CompareSuccess(voice_id=voice_id, clip=clip))
        except VoicesError as exc:
            results.append(CompareFailure(voice_id=voice_id, error=edge_payload_for_error(exc)))
    return results


def render_artifact(context: StudioContext, request: RenderRequest) -> RenderArtifact:
    """Persist one render and return browser download URLs."""
    wav_path = render_speech(
        voice_id=request.voice_id,
        text=request.text,
        language=request.language,
        library=context.library,
        out_dir=context.out_dir,
        expected_reference=request.expected_reference,
        expected_model=request.expected_model,
        compute=context.compute,
    )
    return _artifact_from_path(wav_path)


def export_preview_artifact(context: StudioContext, token: str) -> RenderArtifact:
    """Save the selected preview bytes with generation-time provenance, without inference."""
    return _artifact_from_path(context.asset_store.export_preview(token, context.out_dir))


def _artifact_from_path(wav_path: Path) -> RenderArtifact:
    """Project one persisted output pair into browser download URLs."""
    sidecar_path = wav_path.with_suffix(".json")
    record = OutputRecord.model_validate_json(sidecar_path.read_text(encoding="utf-8"))
    return RenderArtifact(
        record=record,
        audio_url=f"/api/outputs/{record.voice_id}/{wav_path.name}",
        sidecar_url=f"/api/outputs/{record.voice_id}/{sidecar_path.name}",
    )


def prepare_design_voice(context: StudioContext, request: DesignRequest) -> PreparedDesignedVoice:
    """Generate browser design audio without persisting the resulting voice."""
    voice_id = request.voice_id or suggest_voice_id(context.library, request.name)
    return prepare_designed_voice(
        voice_id=voice_id,
        name=request.name,
        instruct=request.instruct,
        text=request.text,
        language=request.language,
        library=context.library,
        overwrite=request.overwrite,
        compute=context.compute,
    )


def save_design_voice(context: StudioContext, prepared: PreparedDesignedVoice, overwrite: bool) -> VoiceDetail:
    """Persist a prepared browser design voice after edge cancellation checks."""
    record = save_prepared_designed_voice(library=context.library, prepared=prepared, overwrite=overwrite)
    return detail_from_record(record)


def _write_upload_to_temp(upload: UploadFile, destination: Path) -> None:
    """Persist one uploaded file to disk for downstream workflows."""
    upload.file.seek(0)
    total_bytes = 0
    with destination.open("wb") as output_file:
        while True:
            chunk = upload.file.read(1_048_576)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > config.MAX_UPLOAD_BYTES:
                max_upload_mib = config.MAX_UPLOAD_BYTES // (1024 * 1024)
                raise InvalidInputError(f"Upload exceeds the {max_upload_mib} MiB local limit.")
            output_file.write(chunk)


def load_batch_design(context: StudioContext, upload: UploadFile, form: BatchDesignForm) -> LoadedBatchDesign:
    """Parse one uploaded prompt pack without creating voices."""
    suffix = Path(upload.filename or "prompts").suffix
    if suffix not in {".jsonl", ".txt"}:
        raise InvalidPromptFileError("Unsupported prompt file format. Use .jsonl or .txt.")
    with tempfile.TemporaryDirectory(prefix="voices-batch-") as temp_dir_name:
        prompt_path = Path(temp_dir_name) / f"upload{suffix}"
        _write_upload_to_temp(upload, prompt_path)
        prompts = load_prompts(prompt_path, default_text=form.text, default_language=form.language)
    return LoadedBatchDesign(prompts=prompts, form=form)


def dry_run_batch_design(loaded: LoadedBatchDesign) -> BatchDesignResult:
    """Project parsed prompts into dry-run browser rows."""
    rows = [
        BatchDesignRow(
            voice_id=prompt.id,
            name=prompt.name or default_display_name(prompt.id),
            status="dry_run",
            detail=prompt.instruct,
        )
        for prompt in loaded.prompts
    ]
    return BatchDesignResult(dry_run=True, rows=rows)


def prepare_batch_prompt_voice(
    context: StudioContext,
    loaded: LoadedBatchDesign,
    prompt: DesignPromptInput,
) -> PreparedDesignedVoice:
    """Generate one prompt-pack row without persisting it."""
    text = prompt.text or loaded.form.text
    if text is None:
        raise InvalidInputError("No seed text provided.")
    return prepare_designed_voice(
        voice_id=prompt.id,
        name=prompt.name or None,
        instruct=prompt.instruct,
        text=text,
        language=prompt.language or loaded.form.language,
        library=context.library,
        overwrite=loaded.form.overwrite,
        compute=context.compute,
    )


def batch_result_from_records(successes: list[VoiceRecord], failures: list[tuple[str, str]]) -> BatchDesignResult:
    """Project batch creation records and failures into the browser contract."""
    rows = [BatchDesignRow(voice_id=record.id, name=record.name, status="ok", detail="Created") for record in successes]
    rows.extend(
        BatchDesignRow(voice_id=voice_id, name="", status="error", detail=detail) for voice_id, detail in failures
    )
    return BatchDesignResult(dry_run=False, rows=rows)


def review_clone_upload(context: StudioContext, upload: UploadFile, form: CloneReviewForm) -> CloneReviewDraft:
    """Normalize one uploaded or browser-recorded clip and return a review draft."""
    suffix = Path(upload.filename or "clip.wav").suffix or ".wav"
    with tempfile.TemporaryDirectory(prefix="voices-review-upload-") as temp_dir_name:
        upload_path = Path(temp_dir_name) / f"source{suffix}"
        _write_upload_to_temp(upload, upload_path)
        fallback_label = Path(upload.filename or "voice").stem.replace("_", " ").replace("-", " ").strip() or "Voice"
        prepared = prepare_clone_review(
            compute=context.compute,
            audio_path=upload_path,
            library=context.library,
            request=CloneReviewRequest(
                language=form.language,
                review_policy=form.review_policy,
                transcript=form.transcript,
                requested_name=form.name,
                requested_voice_id=form.voice_id,
                fallback_name=fallback_label,
            ),
        )
    review_session = context.asset_store.save_review_audio(
        prepared.normalized_audio,
        language=prepared.draft.language,
        suggested_voice_id=prepared.suggested_voice_id,
    )
    return CloneReviewDraft(
        review_token=review_session.review_token,
        suggested_voice_id=prepared.suggested_voice_id,
        transcript=prepared.draft.transcript,
        language=prepared.draft.language,
        duration_seconds=prepared.draft.duration_seconds,
        segments=prepared.draft.segments,
        audio_url=f"/api/assets/{review_session.review_token}.wav",
    )


def save_clone_from_review(context: StudioContext, request: CloneSaveRequest) -> VoiceDetail:
    """Persist one reviewed clone voice."""
    with context.asset_store.claim_review_session(request.review_token) as claimed_review:
        review_session = claimed_review.session
        record = clone_reference_voice(
            voice_id=request.voice_id,
            name=request.name,
            audio_path=review_session.audio_path,
            transcript=request.transcript,
            language=review_session.language,
            library=context.library,
            overwrite=request.overwrite,
        )
        claimed_review.retire()
    return detail_from_record(record)


def delete_voice(context: StudioContext, voice_id: str) -> None:
    """Delete one saved voice from the library."""
    delete_persisted_voice(context.library, voice_id)


def reference_audio_bytes(library: Path, voice_id: str) -> bytes:
    """Return the WAV from one fully validated, coherent reference capture."""
    return load_voice_snapshot(library, voice_id).reference_audio
