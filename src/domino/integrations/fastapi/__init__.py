"""FastAPI integration for Domino's presentation layer.

Optional — install with ``pip install pydomino[fastapi]``. Domino's core has no
runtime dependencies; importing this subpackage requires FastAPI. The unit of
work you wire in is your own — typically the ``domino.integrations.sqlalchemy``
async one (plus an async driver), but any
:class:`~domino.uow.unit_of_work.AsyncUnitOfWork` works.

It wires the presentation layer to the application/domain layers, keeping the
DDD boundaries intact:

- :func:`install_domino` — one call: per-request state, correlation middleware
  and :class:`~domino.core.domain_error.DomainError` → HTTP handlers;
- :data:`UnitOfWorkDep` / :func:`get_unit_of_work` — a fresh unit of work per
  request, built by the factory given to :func:`install_domino` (the route or the
  *use case* opens the transaction scope);
- :class:`CorrelationIdMiddleware` — a correlation id per request, shared by
  every log line and domain event;
- :func:`install_exception_handlers` — map domain errors to status codes;
- :func:`query_filter` / :func:`specifications_from_query` — build
  :mod:`~domino.core.specification` filters from query parameters.

The unit of work dispatches the events queued with ``enqueue_events`` after a
successful commit, when it was built with an ``event_bus``.
"""

from domino.integrations.fastapi.correlation import CorrelationIdMiddleware
from domino.integrations.fastapi.dependencies import UnitOfWorkDep, get_unit_of_work
from domino.integrations.fastapi.errors import (
    DEFAULT_STATUS_MAP,
    install_exception_handlers,
)
from domino.integrations.fastapi.filtering import (
    query_filter,
    specifications_from_query,
)
from domino.integrations.fastapi.state import DominoState
from domino.integrations.fastapi.wiring import install_domino

__all__ = [
    "install_domino",
    "DominoState",
    "get_unit_of_work",
    "UnitOfWorkDep",
    "CorrelationIdMiddleware",
    "install_exception_handlers",
    "DEFAULT_STATUS_MAP",
    "query_filter",
    "specifications_from_query",
]
