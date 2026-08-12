"""AggregateRoot — the consistency boundary for a cluster of domain objects.

An aggregate root is the only entry point for modifying the objects inside its
boundary. On top of :class:`~domino.core.entity.Entity` it records the domain
events produced by its behaviour, ready to be published once the surrounding
transaction commits.

Like any :class:`~domino.core.entity.Entity`, a concrete aggregate is turned
into a mutable dataclass with identity-based equality automatically — no
decorator needed::

    from dataclasses import field
    from datetime import UTC, datetime

    class Order(AggregateRoot):
        _id: DomainId = field(default_factory=DomainId.generate)
        status: str = "draft"
        updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

        def confirm(self) -> None:
            self.status = "confirmed"
            self._touch()
            self._add_event(OrderConfirmed(order_id=self._id))

You do not need to declare a field for the pending events; the base manages
them internally.
"""

from __future__ import annotations

from abc import ABC
from datetime import UTC, datetime

from domino.core.entity import Entity
from domino.events.domain_event import DomainEvent

_EVENTS_ATTR = "_domain_events"


class AggregateRoot(Entity, ABC):
    """Base class for aggregate roots: an entity that records domain events."""

    def _add_event(self, event: DomainEvent) -> None:
        """Record a domain event to be published after the transaction commits."""
        self._events().append(event)

    def pull_pending_events(self) -> list[DomainEvent]:
        """Return the pending events and clear them (call once, then publish)."""
        events = self._events()
        setattr(self, _EVENTS_ATTR, [])
        return events

    def has_pending_events(self) -> bool:
        """Return True if there are recorded events not yet pulled."""
        return bool(getattr(self, _EVENTS_ATTR, None))

    def _touch(self) -> None:
        """Refresh ``updated_at`` (requires the field on the aggregate)."""
        self.updated_at = datetime.now(UTC)

    def _events(self) -> list[DomainEvent]:
        events: list[DomainEvent] | None = getattr(self, _EVENTS_ATTR, None)
        if events is None:
            events = []
            setattr(self, _EVENTS_ATTR, events)
        return events

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(id={self._id!r}, "
            f"pending_events={len(getattr(self, _EVENTS_ATTR, ()))})"
        )
