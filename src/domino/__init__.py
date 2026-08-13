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
from domino.application.use_case import UseCase
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
from domino.events.bus import EventBus
from domino.events.domain_event import DomainEvent
from domino.events.handler import EventHandler, SafeEventHandler
from domino.events.publisher import EventPublisher
from domino.repository.repository import Repository
from domino.services.domain_service import DomainService
from domino.uow.unit_of_work import UnitOfWork

__version__ = "0.1.0"

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
    # Correlation
    "correlation_scope",
    "get_correlation_id",
    "new_correlation_id",
    # Logging
    "get_logger",
    "DominoLogger",
    "LoggerMixin",
    # Aggregate
    "AggregateRoot",
    # Events
    "DomainEvent",
    "EventPublisher",
    "EventHandler",
    "SafeEventHandler",
    "EventBus",
    # Repository
    "Repository",
    # Unit of Work
    "UnitOfWork",
    # Services
    "DomainService",
    # Application
    "Command",
    "UseCase",
]
