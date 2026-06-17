"""Client-side exceptions."""


class VtextClientError(Exception):
    """Base exception for client errors."""


class ServerConnectionError(VtextClientError):
    """Cannot connect to vtext-server."""


class ServerError(VtextClientError):
    """Server returned an error response."""


class QueueFullError(VtextClientError):
    """Server queue is full."""

    def __init__(self, message: str, queue_size: int, estimated_wait: int):
        super().__init__(message)
        self.queue_size = queue_size
        self.estimated_wait = estimated_wait


class TimeoutError(VtextClientError):
    """Request timed out."""
