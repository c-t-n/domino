"""Core DDD building blocks: errors, entities, value objects, IDs, results, and
ambient correlation ids."""

from domino.core.correlation import (
    correlation_scope,
    get_correlation_id,
    new_correlation_id,
)
from domino.core.domain_error import (
    DomainError,
    DomainNotFoundError,
    DomainStateError,
    DomainValidationError,
)
from domino.core.entity import Entity
from domino.core.id import DomainId
from domino.core.logging import DominoLogger, LoggerMixin, get_logger
from domino.core.result import Failure, Result, Success, failure, success
from domino.core.value_object import ValueObject

__all__ = [
    "DomainError",
    "DomainId",
    "DomainNotFoundError",
    "DomainStateError",
    "DomainValidationError",
    "DominoLogger",
    "Entity",
    "Failure",
    "LoggerMixin",
    "Result",
    "Success",
    "ValueObject",
    "correlation_scope",
    "failure",
    "get_correlation_id",
    "get_logger",
    "new_correlation_id",
    "success",
]
