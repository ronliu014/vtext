"""Server-side exceptions."""


class VtextServerError(Exception):
    """Base exception for server errors."""


class TranscriptionError(VtextServerError):
    """whisper.cpp transcription failed."""


class ModelNotFoundError(VtextServerError):
    """Model file not found."""


class DependencyError(VtextServerError):
    """whisper.cpp binary not found or not executable."""
