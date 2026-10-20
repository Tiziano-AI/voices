"""HTTP-safe error payloads and mappings for the local voices edge."""

from fastapi import status
from pydantic import BaseModel, ConfigDict

from voices.domain.errors import (
    AudioConversionError,
    GenerationError,
    InputConflictError,
    InvalidInputError,
    InvalidPromptFileError,
    InvalidVoiceEntryError,
    LibraryIntegrityError,
    MissingDependencyError,
    OperationCancelledError,
    VoiceAlreadyExistsError,
    VoiceNotFoundError,
    VoicesError,
)


class EdgeErrorPayload(BaseModel):
    """Stable browser-facing error envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error_code: str
    detail: str


def edge_status_for_error(error: VoicesError) -> int:
    """Map one domain error into the local HTTP surface."""
    if isinstance(error, (InvalidInputError, InvalidPromptFileError, OperationCancelledError, VoiceAlreadyExistsError)):
        return status.HTTP_400_BAD_REQUEST
    if isinstance(error, VoiceNotFoundError):
        return status.HTTP_404_NOT_FOUND
    if isinstance(error, (InputConflictError, LibraryIntegrityError, InvalidVoiceEntryError)):
        return status.HTTP_409_CONFLICT
    if isinstance(error, (MissingDependencyError, AudioConversionError, GenerationError)):
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def edge_payload_for_error(error: VoicesError) -> EdgeErrorPayload:
    """Project one domain error into the browser payload."""
    return EdgeErrorPayload(error_code=type(error).__name__, detail=str(error))
