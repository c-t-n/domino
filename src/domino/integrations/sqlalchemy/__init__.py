"""SQLAlchemy integration for Domino's infrastructure layer.

Optional — install with ``pip install pydomino[sqlalchemy]``. Domino's core has no
runtime dependencies; importing this subpackage requires SQLAlchemy 2.0+.

It maps pristine Domino domain objects to tables with SQLAlchemy's **imperative
mapping**, so your aggregates, entities and value objects keep zero persistence
awareness — the mapped class *is* your aggregate. Provides:

- :class:`DomainIdType` — a column type for :class:`~domino.core.id.DomainId`;
- :class:`SqlAlchemyRepository` — the ``Repository[T]`` port over a session;
- :class:`SqlAlchemyUnitOfWork` — a unit of work that opens one session per scope;
- :class:`Filterable` — a mixin to query a repository with specifications.

Each of the repository/unit-of-work/filterable pieces has an ``Async*`` twin
(:class:`AsyncSqlAlchemyRepository`, :class:`AsyncSqlAlchemyUnitOfWork`,
:class:`AsyncFilterable`) built on SQLAlchemy's ``AsyncSession`` — use them under
``async with`` with an async driver (aiosqlite, asyncpg, …) and the ``asyncio``
extra (which the ``sqlalchemy`` extra pulls in).

Value objects map with SQLAlchemy's ``composite()`` and aggregate-internal
entities with ``relationship()``; see the documentation for the recipe.
"""

from domino.integrations.sqlalchemy.filtering import AsyncFilterable, Filterable
from domino.integrations.sqlalchemy.outbox import (
    AsyncOutboxRelay,
    Outbox,
    OutboxRelay,
    outbox_table,
)
from domino.integrations.sqlalchemy.repository import (
    AsyncSqlAlchemyRepository,
    SqlAlchemyRepository,
)
from domino.integrations.sqlalchemy.types import DomainIdType
from domino.integrations.sqlalchemy.unit_of_work import (
    AsyncSqlAlchemyUnitOfWork,
    SqlAlchemyUnitOfWork,
)

__all__ = [
    "DomainIdType",
    "Outbox",
    "outbox_table",
    "OutboxRelay",
    "AsyncOutboxRelay",
    "Filterable",
    "SqlAlchemyRepository",
    "SqlAlchemyUnitOfWork",
    "AsyncFilterable",
    "AsyncSqlAlchemyRepository",
    "AsyncSqlAlchemyUnitOfWork",
]
