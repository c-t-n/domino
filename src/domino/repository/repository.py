"""Repository — an abstract, collection-like interface for aggregates.

A repository hides persistence from the domain layer: the domain never sees a
database, ORM or query. One repository serves one aggregate type, returns full
aggregates (never DTOs), and is keyed by identity.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from domino.core.entity import Entity
from domino.core.id import DomainId

T = TypeVar("T", bound=Entity)


class Repository(ABC, Generic[T]):
    """Abstract repository for a single aggregate type.

    Implement it against a concrete store (SQL, document DB, in-memory dict).
    Usage::

        class OrderRepository(Repository[Order]):
            def get_by_id(self, id: DomainId) -> Order | None: ...
            def save(self, aggregate: Order) -> None: ...
            def delete(self, id: DomainId) -> None: ...
    """

    @abstractmethod
    def get_by_id(self, id: DomainId) -> T | None:
        """Return the aggregate with this identity, or ``None`` if absent."""

    @abstractmethod
    def save(self, aggregate: T) -> None:
        """Persist an aggregate, whether new or already stored."""

    @abstractmethod
    def delete(self, id: DomainId) -> None:
        """Remove the aggregate with this identity."""
