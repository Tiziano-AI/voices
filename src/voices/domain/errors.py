"""Domain-specific exceptions and CLI exit codes for the voices product."""

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_MISSING = 3
EXIT_GENERATION = 4
EXIT_INTERNAL = 5


class VoicesError(Exception):
    """Base product error carrying the CLI exit code."""

    code = "voices_error"
    exit_code: int = EXIT_INTERNAL

    def __init__(self, message: str, exit_code: int | None = None) -> None:
        """Create a product error with an optional explicit exit code."""
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class VoiceAlreadyExistsError(VoicesError):
    """The target voice id already exists in the library."""

    code = "voice_already_exists"
    exit_code = EXIT_INPUT


class VoiceNotFoundError(VoicesError):
    """The requested voice id is absent from the library."""

    code = "voice_not_found"
    exit_code = EXIT_MISSING


class InvalidPromptFileError(VoicesError):
    """The batch prompt input file is malformed or unsupported."""

    code = "invalid_prompt_file"
    exit_code = EXIT_INPUT


class InvalidInputError(VoicesError):
    """One CLI, API, or store input violates a public product contract."""

    code = "invalid_input"
    exit_code = EXIT_INPUT


class OperationCancelledError(VoicesError):
    """A browser-scoped operation was canceled before its durable mutation."""

    code = "operation_cancelled"
    exit_code = EXIT_INPUT


class InputConflictError(VoicesError):
    """A caller's selected synthesis inputs changed before generation."""

    code = "input_conflict"
    exit_code = EXIT_INPUT


class InvalidVoiceEntryError(VoicesError):
    """A persisted voice entry is missing assets or fails schema validation."""

    code = "invalid_voice_entry"
    exit_code = EXIT_INTERNAL


class InvalidOutputEntryError(VoicesError):
    """A persisted render output entry is missing assets or fails schema validation."""

    code = "invalid_output_entry"
    exit_code = EXIT_INTERNAL


class LibraryIntegrityError(VoicesError):
    """The voice library contains one or more invalid entries."""

    code = "library_integrity"
    exit_code = EXIT_INTERNAL


class GenerationError(VoicesError):
    """Voice generation failed after entering the MLX runtime boundary."""

    code = "generation"
    exit_code = EXIT_GENERATION


class MissingDependencyError(VoicesError):
    """A required local executable dependency is not available."""

    code = "missing_dependency"
    exit_code = EXIT_INTERNAL


class AudioConversionError(VoicesError):
    """Audio conversion failed before reference assets could be saved."""

    code = "audio_conversion"
    exit_code = EXIT_INTERNAL


class RecordingError(VoicesError):
    """Local microphone capture failed."""

    code = "recording"
    exit_code = EXIT_INTERNAL


class PlaybackError(VoicesError):
    """Local audio playback failed."""

    code = "playback"
    exit_code = EXIT_INTERNAL
