"""EventPublisher — the contract for dispatching domain events.

Implementations may publish in memory, to a background worker, or to a broker
(RabbitMQ, Kafka, ...). :class:`~domino.events.bus.EventBus` is the built-in
in-memory implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domino.events.domain_event import DomainEvent


class EventPublisher(ABC):
    """Interface for publishing domain events."""

    @abstractmethod
    def publish(self, *events: DomainEvent) -> None:
        """Publish one or more domain events."""


class AsyncEventPublisher(ABC):
    """The ``await``-able counterpart, for brokers with an async client.

    A unit of work accepts either: it awaits ``publish`` when the call returns
    an awaitable, so a synchronous :class:`~domino.events.bus.EventBus` still
    works inside an
    :class:`~domino.uow.unit_of_work.AsyncUnitOfWork` — handy in tests.
    """

    @abstractmethod
    async def publish(self, *events: DomainEvent) -> None:
        """Publish one or more domain events."""
