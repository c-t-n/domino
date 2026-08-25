"""One call to wire Domino into a FastAPI app."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from fastapi import FastAPI

from domino.core.domain_error import DomainError
from domino.integrations.fastapi.correlation import CorrelationIdMiddleware
from domino.integrations.fastapi.errors import install_exception_handlers
from domino.integrations.fastapi.state import DominoState
from domino.uow.unit_of_work import AsyncUnitOfWork, UnitOfWork


def install_domino(
    app: FastAPI,
    *,
    unit_of_work: Callable[[], UnitOfWork | AsyncUnitOfWork],
    correlation: bool = True,
    correlation_header: str = "X-Request-ID",
    exception_handlers: bool = True,
    status_map: Mapping[type[DomainError], int] | None = None,
) -> None:
    """Attach Domino's presentation-layer wiring to a FastAPI app.

    - stores the unit-of-work **factory** on ``app.state.domino`` for the
      dependency to call once per request;
    - installs the correlation-id middleware (``correlation=False`` to skip);
    - installs the :class:`DomainError` → HTTP handlers
      (``exception_handlers=False`` to skip).

    ``unit_of_work`` is a zero-arg callable, not an instance: a unit of work holds
    per-scope state (a session, its repositories, the event queue), so each
    request needs its own::

        install_domino(
            app,
            unit_of_work=lambda: AsyncSqlAlchemyUnitOfWork(
                session_factory, {"orders": OrderRepository}, event_bus=bus
            ),
        )

    Long-lived objects — the engine, the ``async_sessionmaker``, the event bus —
    are created once by you (typically in the app's ``lifespan``, where you also
    call ``configure(...)``) and captured by the factory. Only the per-request
    wiring lives here.

    Raises:
        TypeError: if ``unit_of_work`` is not callable (e.g. a unit-of-work
            instance was passed instead of a factory).
    """
    if not callable(unit_of_work):
        raise TypeError(
            "install_domino(unit_of_work=...) expects a zero-arg callable "
            "returning a fresh unit of work, not a unit-of-work instance — "
            "one instance cannot be shared by concurrent requests. "
            "Wrap it: unit_of_work=lambda: MyUnitOfWork(...)"
        )
    app.state.domino = DominoState(unit_of_work)
    if correlation:
        app.add_middleware(CorrelationIdMiddleware, header_name=correlation_header)
    if exception_handlers:
        install_exception_handlers(app, status_map=status_map)
