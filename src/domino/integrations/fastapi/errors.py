"""Translate Domino's :class:`DomainError` hierarchy into HTTP responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from domino.core.correlation import get_correlation_id
from domino.core.domain_error import (
    DomainError,
    DomainNotFoundError,
    DomainStateError,
    DomainValidationError,
)

#: Default mapping of error type to HTTP status. Resolution walks the MRO, so a
#: custom ``DomainError`` subclass falls back to its nearest mapped ancestor.
DEFAULT_STATUS_MAP: dict[type[DomainError], int] = {
    DomainNotFoundError: 404,
    DomainValidationError: 422,
    DomainStateError: 409,
    DomainError: 400,
}


def _status_for(exc_type: type[DomainError], status_map: Mapping[type, int]) -> int:
    for klass in exc_type.__mro__:
        if klass in status_map:
            return status_map[klass]
    return 400


def install_exception_handlers(
    app: FastAPI, *, status_map: Mapping[type[DomainError], int] | None = None
) -> None:
    """Register a handler mapping every :class:`DomainError` to a JSON response.

    The body is ``{"code", "message", "correlation_id"}``. Pass ``status_map`` to
    override or extend :data:`DEFAULT_STATUS_MAP` (merged over the defaults).
    """
    resolved: dict[type, int] = {**DEFAULT_STATUS_MAP, **(status_map or {})}

    async def handle_domain_error(request: Request, exc: Exception) -> Response:
        # Registered only for DomainError, so exc is always one (Starlette's
        # handler signature is typed against the base Exception).
        error = cast("DomainError", exc)
        return JSONResponse(
            status_code=_status_for(type(error), resolved),
            content={
                "code": error.code,
                "message": error.message,
                "correlation_id": get_correlation_id(),
            },
        )

    # Registering the base class is enough: Starlette resolves handlers by MRO,
    # so every subclass is caught too.
    app.add_exception_handler(DomainError, handle_domain_error)
