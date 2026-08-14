"""One call to wire Domino into a FastAPI app."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from domino.core.domain_error import DomainError
from domino.events.publisher import EventPublisher
from domino.integrations.fastapi.correlation import CorrelationIdMiddleware
from domino.integrations.fastapi.errors import install_exception_handlers
from domino.integrations.fastapi.state import DominoState
from domino.integrations.sqlalchemy.async_repository import AsyncSqlAlchemyRepository


def install_domino(
    app: FastAPI,
    *,
    session_factory: Callable[[], AsyncSession],
    repositories: Mapping[str, type[AsyncSqlAlchemyRepository[Any]]],
    event_bus: EventPublisher | None = None,
    correlation: bool = True,
    correlation_header: str = "X-Request-ID",
    exception_handlers: bool = True,
    status_map: Mapping[type[DomainError], int] | None = None,
) -> None:
    """Attach Domino's presentation-layer wiring to a FastAPI app.

    - stores the session factory, repositories and optional event bus on
      ``app.state.domino`` for the unit-of-work dependency to read;
    - installs the correlation-id middleware (``correlation=False`` to skip);
    - installs the :class:`DomainError` → HTTP handlers
      (``exception_handlers=False`` to skip).

    You still create the async engine and ``async_sessionmaker`` yourself
    (typically in the app's ``lifespan``) and call ``configure(...)`` there to set
    Domino's global config. Only the per-request wiring lives here.
    """
    app.state.domino = DominoState(session_factory, dict(repositories), event_bus)
    if correlation:
        app.add_middleware(CorrelationIdMiddleware, header_name=correlation_header)
    if exception_handlers:
        install_exception_handlers(app, status_map=status_map)
