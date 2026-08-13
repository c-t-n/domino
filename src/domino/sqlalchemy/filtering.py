"""``Filterable`` — query a repository with :mod:`domino.core.specification`."""

from __future__ import annotations

import builtins
from typing import Any, Generic, TypeVar

from sqlalchemy import and_, not_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from domino.core.entity import Entity
from domino.core.specification import (
    And,
    FieldCriterion,
    Not,
    Operator,
    Or,
    Specification,
)

T = TypeVar("T", bound=Entity)

_SQL_OPERATORS = {
    Operator.EQ: lambda column, value: column == value,
    Operator.NE: lambda column, value: column != value,
    Operator.LT: lambda column, value: column < value,
    Operator.LE: lambda column, value: column <= value,
    Operator.GT: lambda column, value: column > value,
    Operator.GE: lambda column, value: column >= value,
    Operator.IN: lambda column, value: column.in_(value),
    Operator.LIKE: lambda column, value: column.like(value),
}


class Filterable(Generic[T]):
    """Mixin that adds ``list(*specifications)`` to a ``SqlAlchemyRepository``.

    Mix it in alongside :class:`~domino.sqlalchemy.repository.SqlAlchemyRepository`
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
                and_(*(self._to_clause(spec) for spec in specifications))
            )
        return list(self._session.scalars(query))

    def _to_clause(self, spec: Specification[Any]) -> ColumnElement[bool]:
        if isinstance(spec, FieldCriterion):
            column = getattr(self.aggregate_type, spec.field)
            return _SQL_OPERATORS[spec.operator](column, spec.value)
        if isinstance(spec, And):
            return and_(*(self._to_clause(s) for s in spec.specifications))
        if isinstance(spec, Or):
            return or_(*(self._to_clause(s) for s in spec.specifications))
        if isinstance(spec, Not):
            return not_(self._to_clause(spec.specification))
        raise TypeError(f"unsupported specification: {type(spec).__name__}")
