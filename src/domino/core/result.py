"""Result type for error handling without exceptions.

Use a :class:`Result` when a failure is an expected, in-band outcome (a lookup
that may miss, a validation that may fail) and you would rather return it than
unwind the stack. Keep raising :class:`~domino.core.domain_error.DomainError`
for genuinely exceptional invariant violations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from domino.core.domain_error import DomainError

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E", bound=DomainError)
F = TypeVar("F", bound=DomainError)


class Result(ABC, Generic[T, E]):
    """A computation that either succeeded with a value or failed with an error."""

    @abstractmethod
    def is_success(self) -> bool: ...

    @abstractmethod
    def is_failure(self) -> bool: ...

    @abstractmethod
    def map(self, fn: Callable[[T], U]) -> Result[U, E]:
        """Transform the success value, leaving a failure untouched."""

    @abstractmethod
    def map_error(self, fn: Callable[[E], F]) -> Result[T, F]:
        """Transform the error, leaving a success untouched."""

    @abstractmethod
    def bind(self, fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """Chain another Result-returning computation onto a success."""

    @abstractmethod
    def unwrap(self) -> T:
        """Return the value, or raise the error if this is a failure."""

    @abstractmethod
    def unwrap_or(self, default: T) -> T:
        """Return the value, or ``default`` if this is a failure."""

    @abstractmethod
    def unwrap_error(self) -> E:
        """Return the error, or raise if this is a success."""

    @abstractmethod
    def unwrap_or_else(self, fn: Callable[[E], T]) -> T:
        """Return the value, or the result of ``fn`` applied to the error."""


class Success(Result[T, E]):
    """A successful result holding a value."""

    __slots__ = ("_value",)

    def __init__(self, value: T) -> None:
        self._value = value

    def is_success(self) -> bool:
        return True

    def is_failure(self) -> bool:
        return False

    def map(self, fn: Callable[[T], U]) -> Result[U, E]:
        return Success(fn(self._value))

    def map_error(self, fn: Callable[[E], F]) -> Result[T, F]:
        return Success(self._value)

    def bind(self, fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return fn(self._value)

    def unwrap(self) -> T:
        return self._value

    def unwrap_or(self, default: T) -> T:
        return self._value

    def unwrap_error(self) -> E:
        raise RuntimeError("Called unwrap_error on a Success")

    def unwrap_or_else(self, fn: Callable[[E], T]) -> T:
        return self._value

    def __repr__(self) -> str:
        return f"Success({self._value!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Success) and self._value == other._value

    def __hash__(self) -> int:
        return hash((Success, self._value))


class Failure(Result[T, E]):
    """A failed result holding an error."""

    __slots__ = ("_error",)

    def __init__(self, error: E) -> None:
        self._error = error

    def is_success(self) -> bool:
        return False

    def is_failure(self) -> bool:
        return True

    def map(self, fn: Callable[[T], U]) -> Result[U, E]:
        return Failure(self._error)

    def map_error(self, fn: Callable[[E], F]) -> Result[T, F]:
        return Failure(fn(self._error))

    def bind(self, fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return Failure(self._error)

    def unwrap(self) -> T:
        raise self._error

    def unwrap_or(self, default: T) -> T:
        return default

    def unwrap_error(self) -> E:
        return self._error

    def unwrap_or_else(self, fn: Callable[[E], T]) -> T:
        return fn(self._error)

    def __repr__(self) -> str:
        return f"Failure({self._error!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Failure) and self._error == other._error

    def __hash__(self) -> int:
        return hash((Failure, self._error))


def success(value: T) -> Success[T, Any]:
    """Create a :class:`Success` result."""
    return Success(value)


def failure(error: E) -> Failure[Any, E]:
    """Create a :class:`Failure` result."""
    return Failure(error)
