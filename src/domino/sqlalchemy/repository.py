"""A :class:`~domino.repository.repository.Repository` backed by SQLAlchemy."""

from __future__ import annotations

import typing
from typing import TypeVar

from sqlalchemy.orm import Session

from domino.core.entity import Entity
from domino.core.id import DomainId
from domino.repository.repository import Repository

T = TypeVar("T", bound=Entity)


def _infer_aggregate_type(cls: type) -> type | None:
    """Extract ``X`` from a ``SqlAlchemyRepository[X]`` base, if present."""
    for base in getattr(cls, "__orig_bases__", ()):
        origin = typing.get_origin(base)
        if isinstance(origin, type) and issubclass(origin, SqlAlchemyRepository):
            args = typing.get_args(base)
            if args and isinstance(args[0], type):
                return args[0]
    return None


class SqlAlchemyRepository(Repository[T]):
    """A ``Repository[T]`` implemented against a SQLAlchemy :class:`Session`.

    Subclass it per aggregate — the aggregate type is taken from the generic
    parameter, so there is nothing else to declare::

        class OrderRepository(SqlAlchemyRepository[Order]):
            def by_customer(self, customer_id: DomainId) -> list[Order]:
                return list(self._session.scalars(
                    select(Order).where(Order.customer_id == customer_id)
                ))

    Set the ``aggregate_type`` class attribute explicitly to override inference
    (e.g. when the mapped class differs from the generic parameter). The
    :class:`Session` is injected — normally by
    :class:`~domino.sqlalchemy.unit_of_work.SqlAlchemyUnitOfWork`, one per scope —
    and exposed to subclasses as ``self._session`` for custom queries.

    ``save`` assumes the aggregate was loaded (or created) within the same
    session, which is the unit-of-work norm; for a detached aggregate loaded in a
    previous session, use ``self._session.merge(aggregate)`` instead.
    """

    aggregate_type: type[T]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "aggregate_type" not in cls.__dict__:
            inferred = _infer_aggregate_type(cls)
            if inferred is not None:
                # Resolved by runtime introspection of the generic parameter.
                cls.aggregate_type = inferred  # ty: ignore[invalid-assignment]

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, id: DomainId) -> T | None:
        return self._session.get(self.aggregate_type, id)

    def save(self, aggregate: T) -> None:
        self._session.add(aggregate)

    def delete(self, id: DomainId) -> None:
        aggregate = self.get_by_id(id)
        if aggregate is not None:
            self._session.delete(aggregate)
