"""Application error carried to the HTTP layer as a stable envelope."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details
        self.headers = headers or {}


def too_many(code: str, message: str, retry_after: float, status: int = 429, details: Any = None) -> ApiError:
    """429 (or 503) carrying a Retry-After header of at least one second."""
    return ApiError(status, code, message, details, headers={"Retry-After": str(max(1, int(retry_after + 0.999)))})


def require(condition: Any, status: int, code: str, message: str, details: Any = None) -> None:
    if not condition:
        raise ApiError(status, code, message, details)
