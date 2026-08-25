"""Domain events and event handling infrastructure."""

from domino.events.bus import EventBus
from domino.events.domain_event import DomainEvent
from domino.events.handler import EventHandler, SafeEventHandler
from domino.events.publisher import EventPublisher
from domino.events.serialization import EventRegistry, SerializationError

__all__ = [
    "DomainEvent",
    "EventBus",
    "EventHandler",
    "EventPublisher",
    "SafeEventHandler",
    "EventRegistry",
    "SerializationError",
]
