"""SQLAlchemy integration for Domino's infrastructure layer.

Optional — install with ``pip install domino[sqlalchemy]``. Domino's core has no
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

from domino.sqlalchemy.async_filtering import AsyncFilterable
from domino.sqlalchemy.async_repository import AsyncSqlAlchemyRepository
from domino.sqlalchemy.async_unit_of_work import AsyncSqlAlchemyUnitOfWork
from domino.sqlalchemy.filtering import Filterable
from domino.sqlalchemy.repository import SqlAlchemyRepository
from domino.sqlalchemy.types import DomainIdType
from domino.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork

__all__ = [
    "DomainIdType",
    "Filterable",
    "SqlAlchemyRepository",
    "SqlAlchemyUnitOfWork",
    "AsyncFilterable",
    "AsyncSqlAlchemyRepository",
    "AsyncSqlAlchemyUnitOfWork",
]
