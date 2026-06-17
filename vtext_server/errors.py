"""Server-side exception definitions."""


class VtextServerError(Exception):
    """Base exception for all server errors."""
    pass


class TranscriptionError(VtextServerError):
    """Raised when whisper.cpp transcription fails."""
    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


class AudioConversionError(VtextServerError):
    """Raised when WAV conversion fails."""
    pass


class ModelNotFoundError(VtextServerError):
    """Raised when requested model is not available."""
    def __init__(self, message: str):
        super().__init__(message)


class DependencyError(VtextServerError):
    """Raised when a required external binary (whisper.cpp, ffmpeg) is missing."""
    pass


class ModelLoadError(VtextServerError):
    """Raised when model cannot be loaded."""
    pass


class QueueFullError(VtextServerError):
    """Raised when the job queue is at capacity."""
    def __init__(self, queue_size: int, max_size: int, estimated_wait_seconds: float):
        super().__init__(f"Queue full ({queue_size}/{max_size} jobs)")
        self.queue_size = queue_size
        self.max_size = max_size
        self.estimated_wait_seconds = estimated_wait_seconds


class JobNotFoundError(VtextServerError):
    """Raised when a job ID does not exist."""
    def __init__(self, job_id: str):
        super().__init__(f"Job '{job_id}' not found")
        self.job_id = job_id


class DecompressionError(VtextServerError):
    """Raised when zstd decompression fails."""
    pass
