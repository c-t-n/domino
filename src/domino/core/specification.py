"""Specifications: composable, persistence-ignorant filter criteria.

A specification captures a predicate over domain objects. Build one with the
field helpers (:func:`eq`, :func:`lt`, :func:`in_` …), compose with ``&`` / ``|``
/ ``~``, and evaluate it in memory with :meth:`Specification.is_satisfied_by`::

    active = eq("status", "active") & gt("age", 18)
    active.is_satisfied_by(user)   # -> bool

The optional SQLAlchemy integration translates the same specification into a SQL
``WHERE`` clause (see :class:`domino.sqlalchemy.Filterable`), so one set of
criteria drives both an in-memory check and a database query. Criteria filter on
attribute names, so the field names must exist on the object (and, for SQL, be
mapped columns).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class Specification(ABC, Generic[T]):
    """A composable predicate over ``T``."""

    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool:
        """Return True if ``candidate`` matches this specification."""

    def __and__(self, other: Specification[T]) -> Specification[T]:
        return And((self, other))

    def __or__(self, other: Specification[T]) -> Specification[T]:
        return Or((self, other))

    def __invert__(self) -> Specification[T]:
        return Not(self)


class Operator(Enum):
    """The comparison a :class:`FieldCriterion` applies."""

    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    IN = "in"
    LIKE = "like"


def _like(value: Any, pattern: str) -> bool:
    # SQL LIKE semantics: % = any run, _ = one char. Case-sensitive in memory;
    # in SQL, case sensitivity follows the database.
    regex = "^" + re.escape(str(pattern)).replace("%", ".*").replace("_", ".") + "$"
    return re.match(regex, str(value)) is not None


_EVALUATORS: dict[Operator, Callable[[Any, Any], bool]] = {
    Operator.EQ: lambda a, b: bool(a == b),
    Operator.NE: lambda a, b: bool(a != b),
    Operator.LT: lambda a, b: a < b,
    Operator.LE: lambda a, b: a <= b,
    Operator.GT: lambda a, b: a > b,
    Operator.GE: lambda a, b: a >= b,
    Operator.IN: lambda a, b: a in b,
    Operator.LIKE: _like,
}


@dataclass(frozen=True)
class FieldCriterion(Specification[Any]):
    """A single ``field <operator> value`` comparison."""

    field: str
    operator: Operator
    value: Any

    def is_satisfied_by(self, candidate: Any) -> bool:
        return _EVALUATORS[self.operator](getattr(candidate, self.field), self.value)


@dataclass(frozen=True)
class And(Specification[Any]):
    """All of the given specifications must hold."""

    specifications: tuple[Specification[Any], ...]

    def is_satisfied_by(self, candidate: Any) -> bool:
        return all(spec.is_satisfied_by(candidate) for spec in self.specifications)


@dataclass(frozen=True)
class Or(Specification[Any]):
    """Any of the given specifications must hold."""

    specifications: tuple[Specification[Any], ...]

    def is_satisfied_by(self, candidate: Any) -> bool:
        return any(spec.is_satisfied_by(candidate) for spec in self.specifications)


@dataclass(frozen=True)
class Not(Specification[Any]):
    """The given specification must not hold."""

    specification: Specification[Any]

    def is_satisfied_by(self, candidate: Any) -> bool:
        return not self.specification.is_satisfied_by(candidate)


def eq(field: str, value: Any) -> Specification[Any]:
    """``field == value``."""
    return FieldCriterion(field, Operator.EQ, value)


def ne(field: str, value: Any) -> Specification[Any]:
    """``field != value``."""
    return FieldCriterion(field, Operator.NE, value)


def lt(field: str, value: Any) -> Specification[Any]:
    """``field < value``."""
    return FieldCriterion(field, Operator.LT, value)


def le(field: str, value: Any) -> Specification[Any]:
    """``field <= value``."""
    return FieldCriterion(field, Operator.LE, value)


def gt(field: str, value: Any) -> Specification[Any]:
    """``field > value``."""
    return FieldCriterion(field, Operator.GT, value)


def ge(field: str, value: Any) -> Specification[Any]:
    """``field >= value``."""
    return FieldCriterion(field, Operator.GE, value)


def in_(field: str, values: Iterable[Any]) -> Specification[Any]:
    """``field in values``."""
    return FieldCriterion(field, Operator.IN, tuple(values))


def like(field: str, pattern: str) -> Specification[Any]:
    """SQL ``LIKE`` match (``%`` = any run, ``_`` = one char)."""
    return FieldCriterion(field, Operator.LIKE, pattern)
