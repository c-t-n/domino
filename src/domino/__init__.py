"""domino — a small library for Domain-Driven Design in Python.

Provides base classes for the tactical DDD patterns: entities, value objects,
aggregates, repositories, domain services, use cases, a unit of work, and
domain events with an in-memory event bus.

Subclass a base and declare fields — no ``@dataclass`` decorator needed, the
bases apply it for you (with full static typing via PEP 681).

Quickstart::

    from decimal import Decimal

    from domino import ValueObject

    class Money(ValueObject):
        amount: Decimal
        currency: str
"""

from domino.aggregate.aggregate_root import AggregateRoot
from domino.application.command import Command
from domino.application.use_case import AsyncUseCase, UseCase
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
from domino.events.bus import AsyncEventBus, EventBus
from domino.events.domain_event import DomainEvent
from domino.events.handler import (
    AsyncEventHandler,
    EventHandler,
    SafeAsyncEventHandler,
    SafeEventHandler,
)
from domino.events.publisher import AsyncEventPublisher, EventPublisher
from domino.events.serialization import EventRegistry, SerializationError
from domino.repository.repository import AsyncRepository, Repository
from domino.services.domain_service import DomainService
from domino.uow.unit_of_work import AsyncUnitOfWork, UnitOfWork

__version__ = "0.2.0"

__all__ = [
    # Core
    "DomainError",
    "DomainValidationError",
    "DomainStateError",
    "DomainNotFoundError",
    "Entity",
    "ValueObject",
    "DomainId",
    "Result",
    "Success",
    "Failure",
    "success",
    "failure",
    # Specification
    "Specification",
    "eq",
    "ne",
    "lt",
    "le",
    "gt",
    "ge",
    "in_",
    "like",
    # Correlation
    "correlation_scope",
    "get_correlation_id",
    "new_correlation_id",
    # Logging
    "get_logger",
    "DominoLogger",
    "LoggerMixin",
    # Configuration
    "configure",
    "get_config",
    "reset_config",
    "DominoConfig",
    # Aggregate
    "AggregateRoot",
    # Events
    "DomainEvent",
    "EventPublisher",
    "AsyncEventPublisher",
    "EventHandler",
    "AsyncEventHandler",
    "SafeEventHandler",
    "SafeAsyncEventHandler",
    "EventBus",
    "AsyncEventBus",
    "EventRegistry",
    "SerializationError",
    # Repository
    "Repository",
    "AsyncRepository",
    # Unit of Work
    "UnitOfWork",
    "AsyncUnitOfWork",
    # Services
    "DomainService",
    # Application
    "Command",
    "UseCase",
    "AsyncUseCase",
]
