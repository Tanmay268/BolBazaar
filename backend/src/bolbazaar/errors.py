"""Application error carried to the HTTP layer as a stable envelope."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details


def require(condition: Any, status: int, code: str, message: str, details: Any = None) -> None:
    if not condition:
        raise ApiError(status, code, message, details)
