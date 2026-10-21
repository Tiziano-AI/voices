import threading
import webbrowser
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, File, Form, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from voices import config
from voices.domain.contracts import VoiceRecord
from voices.domain.errors import InvalidInputError, OperationCancelledError, VoicesError
from voices.edge.contracts import (
    BatchDesignForm,
    CloneReviewForm,
    CloneSaveRequest,
    CompareRequest,
    DesignRequest,
    OutputDownloadTarget,
    PreviewRequest,
    RenderRequest,
    UiConfigResponse,
)
from voices.edge.errors import edge_payload_for_error, edge_status_for_error
from voices.edge.local_admission import LOOPBACK_HOSTS, MUTATING_METHODS, local_request_error
from voices.edge.service import (
    OperationCancellationRegistry,
    StudioContext,
    batch_result_from_records,
    create_compare_clips,
    create_preview_clip,
    delete_voice,
    dry_run_batch_design,
    export_preview_artifact,
    list_voice_summaries,
    load_batch_design,
    load_voice_detail,
    prepare_batch_prompt_voice,
    prepare_design_voice,
    reference_audio_bytes,
    render_artifact,
    review_clone_upload,
    save_clone_from_review,
    save_design_voice,
)
from voices.edge.storage import StudioAssetStore
from voices.store.output_store import resolve_output_path
from voices.studio_bundle import resolve_web_dist


@dataclass(frozen=True, slots=True)
class LaunchOptions:
    """Resolved options for the local studio launcher."""

    host: str
    port: int
    open_browser: bool


MAX_MULTIPART_OVERHEAD_BYTES = 64 * 1024


def require_loopback_host(host: str) -> str:
    """Validate that the bundled studio binds only to a loopback host."""
    normalized = host.strip().lower()
    if normalized not in LOOPBACK_HOSTS:
        raise InvalidInputError("The bundled studio only binds to loopback hosts: 127.0.0.1, localhost, or ::1.")
    return normalized


def loopback_url(host: str, port: int) -> str:
    """Build the browser URL for one validated loopback listener."""
    resolved_host = require_loopback_host(host)
    display_host = f"[{resolved_host}]" if ":" in resolved_host else resolved_host
    return f"http://{display_host}:{port}"


@asynccontextmanager
async def _edge_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own temp asset cleanup for the edge process."""
    try:
        yield
    finally:
        context = app.state.context
        if isinstance(context, StudioContext):
            context.asset_store.cleanup()


def _handle_domain_error(error: VoicesError) -> JSONResponse:
    """Project one domain error into the browser HTTP surface."""
    return JSONResponse(
        status_code=edge_status_for_error(error),
        content=edge_payload_for_error(error).model_dump(mode="json"),
    )


def _validation_response(error: RequestValidationError | ValidationError) -> JSONResponse:
    """Normalize FastAPI validation failures into the browser error envelope."""
    details: list[str] = []
    for line in str(error).splitlines():
        stripped = line.strip()
        if stripped:
            details.append(stripped)
    detail = "; ".join(details) if details else "Invalid request."
    return JSONResponse(status_code=400, content={"error_code": "RequestValidationError", "detail": detail})


def _multipart_content_length_too_large(request: Request) -> bool:
    """Return whether a browser multipart request declares an impossible upload size."""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.lower():
        return False
    content_length = request.headers.get("content-length")
    if content_length is None:
        return False
    try:
        declared_bytes = int(content_length)
    except ValueError:
        return False
    return declared_bytes > config.MAX_UPLOAD_BYTES + MAX_MULTIPART_OVERHEAD_BYTES


async def _raise_if_disconnected(request: Request) -> None:
    """Fail before persistence when the browser has canceled the request."""
    if await request.is_disconnected():
        raise InvalidInputError("Browser request was canceled before persistence.")


def _raise_if_cancelled(context: StudioContext, operation_token: str | None) -> None:
    """Fail before persistence when the browser explicitly canceled the operation."""
    if context.cancellations.is_cancelled(operation_token):
        context.cancellations.forget(operation_token)
        raise OperationCancelledError("Browser request was canceled before persistence.")


def create_edge_app(*, library: Path, out_dir: Path, web_dist: Path | None = None) -> FastAPI:
    """Create the local studio FastAPI app for one configured library root."""
    app = FastAPI(title="voices studio", lifespan=_edge_lifespan)
    app.state.context = StudioContext(
        library=library,
        out_dir=out_dir,
        asset_store=StudioAssetStore(),
        cancellations=OperationCancellationRegistry(),
    )

    @app.exception_handler(VoicesError)
    async def handle_voices_error(_request: object, error: VoicesError) -> JSONResponse:
        return _handle_domain_error(error)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: object, error: RequestValidationError) -> JSONResponse:
        return _validation_response(error)

    @app.exception_handler(ValidationError)
    async def handle_pydantic_validation_error(_request: object, error: ValidationError) -> JSONResponse:
        return _validation_response(error)

    @app.exception_handler(status.HTTP_400_BAD_REQUEST)
    async def handle_bad_request(_request: object, error: HTTPException) -> JSONResponse:
        """Keep upstream form-parser rejections in the browser error envelope."""
        return JSONResponse(
            status_code=error.status_code,
            content={"error_code": "RequestValidationError", "detail": error.detail},
            headers=error.headers,
        )

    @app.middleware("http")
    async def enforce_local_listener(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        admission_error = local_request_error(request)
        if admission_error is not None:
            return _handle_domain_error(InvalidInputError(admission_error))
        if request.method in MUTATING_METHODS and _multipart_content_length_too_large(request):
            max_upload_mib = config.MAX_UPLOAD_BYTES // (1024 * 1024)
            return _handle_domain_error(InvalidInputError(f"Upload exceeds the {max_upload_mib} MiB local limit."))
        return await call_next(request)

    @app.get("/api/ui-config", response_model=UiConfigResponse)
    async def ui_config() -> UiConfigResponse:
        return UiConfigResponse()

    @app.post("/api/operations/{operation_token}/cancel", status_code=status.HTTP_204_NO_CONTENT)
    async def operation_cancel(operation_token: str) -> Response:
        context = app.state.context
        context.cancellations.cancel(operation_token)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/voices")
    async def voices() -> list[dict[str, object]]:
        context = app.state.context
        summaries = await run_in_threadpool(list_voice_summaries, context.library)
        return [summary.model_dump(mode="json") for summary in summaries]

    @app.get("/api/voices/{voice_id}")
    async def voice_detail(voice_id: str) -> dict[str, object]:
        context = app.state.context
        detail = await run_in_threadpool(load_voice_detail, context.library, voice_id)
        return detail.model_dump(mode="json")

    @app.get("/api/voices/{voice_id}/reference-audio")
    async def voice_reference_audio(voice_id: str) -> Response:
        context = app.state.context
        audio = await run_in_threadpool(reference_audio_bytes, context.library, voice_id)
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={"Content-Disposition": f'attachment; filename="{voice_id}-reference.wav"'},
        )

    @app.get("/api/assets/{token}.wav")
    async def asset_audio(token: str) -> FileResponse:
        context = app.state.context
        path = context.asset_store.asset_path(token)
        return FileResponse(path=path, media_type="audio/wav", filename=path.name)

    @app.post("/api/preview")
    async def preview(request: PreviewRequest) -> dict[str, object]:
        context = app.state.context
        clip = await run_in_threadpool(create_preview_clip, context, request)
        return clip.model_dump(mode="json")

    @app.post("/api/compare")
    async def compare(request: CompareRequest) -> list[dict[str, object]]:
        context = app.state.context
        results = await run_in_threadpool(create_compare_clips, context, request)
        return [result.model_dump(mode="json") for result in results]

    @app.post("/api/previews/{token}/export")
    async def export_preview(token: str) -> dict[str, object]:
        context = app.state.context
        artifact = await run_in_threadpool(export_preview_artifact, context, token)
        return artifact.model_dump(mode="json")

    @app.post("/api/render")
    async def render(request: RenderRequest) -> dict[str, object]:
        context = app.state.context
        artifact = await run_in_threadpool(render_artifact, context, request)
        return artifact.model_dump(mode="json")

    @app.get("/api/outputs/{voice_id}/{filename}")
    async def output_file(voice_id: str, filename: str) -> FileResponse:
        context = app.state.context
        target = OutputDownloadTarget(voice_id=voice_id, filename=filename)
        path = resolve_output_path(context.out_dir, target.voice_id, target.filename)
        media_type = "application/json" if path.suffix == ".json" else "audio/wav"
        return FileResponse(path=path, media_type=media_type, filename=path.name)

    @app.post("/api/design")
    async def design(request: Request, payload: DesignRequest) -> dict[str, object]:
        context = app.state.context
        prepared = await run_in_threadpool(prepare_design_voice, context, payload)
        try:
            _raise_if_cancelled(context, payload.operation_token)
            await _raise_if_disconnected(request)
            detail = await run_in_threadpool(save_design_voice, context, prepared, payload.overwrite)
            return detail.model_dump(mode="json")
        finally:
            context.cancellations.forget(payload.operation_token)

    @app.post("/api/design/batch")
    async def design_batch(
        request: Request,
        file: UploadFile = File(...),
        language: str = Form(config.DEFAULT_LANGUAGE),
        text: str | None = Form(None),
        overwrite: bool = Form(False),
        dry_run: bool = Form(False),
        operation_token: str | None = Form(None),
    ) -> dict[str, object]:
        context = app.state.context
        form = BatchDesignForm(
            language=language,
            text=text,
            overwrite=overwrite,
            dry_run=dry_run,
            operation_token=operation_token,
        )
        loaded = await run_in_threadpool(load_batch_design, context, file, form)
        if loaded.form.dry_run:
            try:
                return dry_run_batch_design(loaded).model_dump(mode="json")
            finally:
                context.cancellations.forget(loaded.form.operation_token)
        successes: list[VoiceRecord] = []
        failures: list[tuple[str, str]] = []
        try:
            for prompt in loaded.prompts:
                try:
                    prepared = await run_in_threadpool(prepare_batch_prompt_voice, context, loaded, prompt)
                    _raise_if_cancelled(context, loaded.form.operation_token)
                    await _raise_if_disconnected(request)
                    detail = await run_in_threadpool(save_design_voice, context, prepared, loaded.form.overwrite)
                    successes.append(detail.record)
                except OperationCancelledError:
                    raise
                except VoicesError as exc:
                    failures.append((prompt.id, str(exc)))
            return batch_result_from_records(successes, failures).model_dump(mode="json")
        finally:
            context.cancellations.forget(loaded.form.operation_token)

    @app.post("/api/clone/review")
    async def clone_review(
        audio: UploadFile = File(...),
        language: str = Form(config.DEFAULT_LANGUAGE),
        review_policy: Literal["import", "record_guided", "record_free"] = Form("import"),
        transcript: str | None = Form(None),
        name: str | None = Form(None),
        voice_id: str | None = Form(None),
    ) -> dict[str, object]:
        context = app.state.context
        form = CloneReviewForm(
            language=language,
            review_policy=review_policy,
            transcript=transcript,
            name=name,
            voice_id=voice_id,
        )
        draft = await run_in_threadpool(review_clone_upload, context, audio, form)
        return draft.model_dump(mode="json")

    @app.post("/api/clone/save")
    async def clone_save(request: CloneSaveRequest) -> dict[str, object]:
        context = app.state.context
        detail = await run_in_threadpool(save_clone_from_review, context, request)
        return detail.model_dump(mode="json")

    @app.delete("/api/voices/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def voice_delete(voice_id: str) -> Response:
        context = app.state.context
        await run_in_threadpool(delete_voice, context, voice_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if web_dist is not None:
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="studio")

    return app


def _open_browser(url: str) -> None:
    """Open the browser asynchronously after the edge server starts."""
    webbrowser.open(url)


def launch_edge_server(*, library: Path, out_dir: Path, launch: LaunchOptions) -> None:
    """Launch the bundled local browser studio."""
    web_dist = resolve_web_dist()
    host = require_loopback_host(launch.host)
    app = create_edge_app(library=library, out_dir=out_dir, web_dist=web_dist)
    url = loopback_url(host, launch.port)
    if launch.open_browser:
        opener = threading.Timer(interval=0.8, function=_open_browser, args=[url])
        opener.daemon = True
        opener.start()
    uvicorn.run(app, host=host, port=launch.port, log_level="warning", proxy_headers=False)
