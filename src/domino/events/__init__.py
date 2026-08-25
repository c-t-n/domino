"""Domain events and event handling infrastructure."""

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

__all__ = [
    "DomainEvent",
    "EventBus",
    "AsyncEventBus",
    "EventHandler",
    "AsyncEventHandler",
    "EventPublisher",
    "AsyncEventPublisher",
    "SafeEventHandler",
    "SafeAsyncEventHandler",
    "EventRegistry",
    "SerializationError",
]
