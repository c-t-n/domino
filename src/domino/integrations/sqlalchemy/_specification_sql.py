"""Translate a :mod:`domino.core.specification` into a SQLAlchemy WHERE clause.

Shared by the sync and async ``Filterable`` mixins — the translation is
identical, only the session call (``scalars`` vs ``await scalars``) differs.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, not_, or_
from sqlalchemy.sql.elements import ColumnElement

from domino.core.specification import (
    And,
    FieldCriterion,
    Not,
    Operator,
    Or,
    Specification,
)

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


def to_clause(aggregate_type: type, spec: Specification[Any]) -> ColumnElement[bool]:
    """Turn one specification into a SQL boolean clause on ``aggregate_type``."""
    if isinstance(spec, FieldCriterion):
        column = getattr(aggregate_type, spec.field)
        return _SQL_OPERATORS[spec.operator](column, spec.value)
    if isinstance(spec, And):
        return and_(*(to_clause(aggregate_type, s) for s in spec.specifications))
    if isinstance(spec, Or):
        return or_(*(to_clause(aggregate_type, s) for s in spec.specifications))
    if isinstance(spec, Not):
        return not_(to_clause(aggregate_type, spec.specification))
    raise TypeError(f"unsupported specification: {type(spec).__name__}")
