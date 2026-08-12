"""Domain-specific exception hierarchy.

Every domain error inherits from :class:`DomainError`. Subclasses distinguish
validation failures from state transitions and lookups so the outer layers
(HTTP, CLI, messaging) can translate them consistently.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base exception for all domain-level errors.

    Raise this (or a subclass) whenever a business rule is violated. The
    ``code`` defaults to the class name, giving a machine-readable identifier
    the presentation layer can map to an HTTP status or a translated message.
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self._default_code()

    def _default_code(self) -> str:
        return type(self).__name__

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DomainError):
            return NotImplemented
        return type(self) is type(other) and (self.message, self.code) == (
            other.message,
            other.code,
        )

    def __hash__(self) -> int:
        return hash((type(self), self.message, self.code))


class DomainValidationError(DomainError):
    """Input data violates a domain constraint (e.g. negative quantity)."""

    def _default_code(self) -> str:
        return "VALIDATION_ERROR"


class DomainStateError(DomainError):
    """A state transition is invalid (e.g. shipping a cancelled order)."""

    def _default_code(self) -> str:
        return "STATE_ERROR"


class DomainNotFoundError(DomainError):
    """A requested aggregate or entity does not exist."""

    def _default_code(self) -> str:
        return "NOT_FOUND"
