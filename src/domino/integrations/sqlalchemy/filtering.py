"""``Filterable`` — query a repository with :mod:`domino.core.specification`."""

from __future__ import annotations

import builtins
from typing import Any, Generic, TypeVar

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from domino.core.entity import Entity
from domino.core.specification import Specification
from domino.integrations.sqlalchemy._specification_sql import to_clause

T = TypeVar("T", bound=Entity)


class Filterable(Generic[T]):
    """Mixin that adds ``list(*specifications)`` to a ``SqlAlchemyRepository``.

    Mix it in alongside
    :class:`~domino.integrations.sqlalchemy.repository.SqlAlchemyRepository`
    (it reuses that class's ``aggregate_type`` and session)::

        class OrderRepository(SqlAlchemyRepository[Order], Filterable[Order]):
            ...

        repo.list(eq("status", "confirmed"), in_("customer_id", [c1, c2]))
        repo.list(gt("total", 100) | eq("vip", True))
        repo.list()  # everything

    Positional specifications are AND-ed together; use ``&`` / ``|`` / ``~`` to
    build richer predicates. The same specifications also work in memory via
    :meth:`~domino.core.specification.Specification.is_satisfied_by`.
    """

    aggregate_type: type[T]
    _session: Session

    def list(self, *specifications: Specification[Any]) -> builtins.list[T]:
        """Return every aggregate matching all the given specifications."""
        query = select(self.aggregate_type)
        if specifications:
            query = query.where(
                and_(*(to_clause(self.aggregate_type, s) for s in specifications))
            )
        return list(self._session.scalars(query))
