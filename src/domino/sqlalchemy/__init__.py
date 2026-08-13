"""SQLAlchemy integration for Domino's infrastructure layer.

Optional — install with ``pip install domino[sqlalchemy]``. Domino's core has no
runtime dependencies; importing this subpackage requires SQLAlchemy 2.0+.

It maps pristine Domino domain objects to tables with SQLAlchemy's **imperative
mapping**, so your aggregates, entities and value objects keep zero persistence
awareness — the mapped class *is* your aggregate. Provides:

- :class:`DomainIdType` — a column type for :class:`~domino.core.id.DomainId`;
- :class:`SqlAlchemyRepository` — the ``Repository[T]`` port over a session;
- :class:`SqlAlchemyUnitOfWork` — a unit of work that opens one session per scope.

Value objects map with SQLAlchemy's ``composite()`` and aggregate-internal
entities with ``relationship()``; see the documentation for the recipe.
"""

from domino.sqlalchemy.repository import SqlAlchemyRepository
from domino.sqlalchemy.types import DomainIdType
from domino.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork

__all__ = [
    "DomainIdType",
    "SqlAlchemyRepository",
    "SqlAlchemyUnitOfWork",
]
