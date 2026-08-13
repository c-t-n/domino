"""Core DDD building blocks: errors, entities, value objects, IDs, results, and
ambient correlation ids."""

from domino.core.config import DominoConfig, configure, get_config, reset_config
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
from domino.core.specification import (
    Specification,
    eq,
    ge,
    gt,
    in_,
    le,
    like,
    lt,
    ne,
)
from domino.core.value_object import ValueObject

__all__ = [
    "DomainError",
    "DomainId",
    "DomainNotFoundError",
    "DomainStateError",
    "DomainValidationError",
    "DominoConfig",
    "DominoLogger",
    "Entity",
    "Failure",
    "LoggerMixin",
    "Result",
    "Specification",
    "Success",
    "ValueObject",
    "configure",
    "eq",
    "ge",
    "gt",
    "in_",
    "le",
    "like",
    "lt",
    "ne",
    "correlation_scope",
    "failure",
    "get_config",
    "get_correlation_id",
    "get_logger",
    "new_correlation_id",
    "reset_config",
    "success",
]
