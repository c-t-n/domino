"""FastAPI integration for Domino's presentation layer.

Optional — install with ``pip install domino[fastapi]``. Domino's core has no
runtime dependencies; importing this subpackage requires FastAPI (and, for the
unit of work, the ``domino.integrations.sqlalchemy`` async pieces + an async driver).

It wires the presentation layer to the application/domain layers, keeping the
DDD boundaries intact:

- :func:`install_domino` — one call: per-request state, correlation middleware
  and :class:`~domino.core.domain_error.DomainError` → HTTP handlers;
- :data:`UnitOfWorkDep` / :func:`get_unit_of_work` — a fresh unit of work per
  request (the *use case* still owns the transaction);
- :class:`CorrelationIdMiddleware` — a correlation id per request, shared by
  every log line and domain event;
- :func:`install_exception_handlers` — map domain errors to status codes;
- :func:`query_filter` / :func:`specifications_from_query` — build
  :mod:`~domino.core.specification` filters from query parameters.

The unit of work dispatches domain events after commit when an ``event_bus`` is
passed to :func:`install_domino`.
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
