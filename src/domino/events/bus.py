"""EventBus — in-memory routing of domain events to handlers.

Register handlers by event type and publish events to them synchronously.
Every handler is wrapped in :class:`SafeEventHandler`, so one failing handler
never stops the others or propagates to the caller.

:class:`AsyncEventBus` is the same thing for an async stack: ``publish`` is a
coroutine and handlers may be awaited.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import cast

from domino.events.domain_event import DomainEvent
from domino.events.handler import (
    AsyncEventHandler,
    EventHandler,
    SafeAsyncEventHandler,
    SafeEventHandler,
)
from domino.events.publisher import AsyncEventPublisher, EventPublisher

HandlerMapping = (
    Mapping[type[DomainEvent], EventHandler]
    | Iterable[tuple[type[DomainEvent], EventHandler]]
)
AnyHandler = EventHandler | AsyncEventHandler
AnyHandlerMapping = (
    Mapping[type[DomainEvent], AnyHandler]
    | Iterable[tuple[type[DomainEvent], AnyHandler]]
)


class EventBus(EventPublisher):
    """In-memory event bus routing events to registered handlers.

    Usage::

        bus = EventBus()
        bus.register(OrderConfirmed, InventoryHandler())
        bus.register(OrderConfirmed, EmailHandler())  # many handlers per event
        bus.publish(*order.pull_pending_events())
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[SafeEventHandler]] = defaultdict(
            list
        )

    def register(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        """Register a handler for an event type (multiple handlers allowed)."""
        self._handlers[event_type].append(SafeEventHandler(handler))

    def register_all(self, handlers: HandlerMapping) -> None:
        """Register several handlers from a mapping or an iterable of pairs."""
        pairs: Iterable[tuple[type[DomainEvent], EventHandler]]
        if isinstance(handlers, Mapping):
            # A Mapping yields its keys when iterated, so use items() for pairs.
            pairs = cast(
                "Iterable[tuple[type[DomainEvent], EventHandler]]", handlers.items()
            )
        else:
            pairs = handlers
        for event_type, handler in pairs:
            self.register(event_type, handler)

    def publish(self, *events: DomainEvent) -> None:
        """Dispatch each event to every handler registered for its type."""
        for event in events:
            for handler in self._handlers.get(type(event), ()):
                handler.handle(event)

    def clear(self) -> None:
        """Remove all registered handlers."""
        self._handlers.clear()

    def handler_count(self, event_type: type[DomainEvent] | None = None) -> int:
        """Number of handlers registered, for one event type or in total."""
        if event_type is None:
            return sum(len(handlers) for handlers in self._handlers.values())
        return len(self._handlers.get(event_type, ()))


class AsyncEventBus(AsyncEventPublisher):
    """In-memory event bus that awaits its handlers.

    The async counterpart of :class:`EventBus`: same registration API, but
    ``publish`` is a coroutine, so handlers can do IO. Sync and async handlers
    can be mixed — a sync one is called directly, an async one is awaited::

        bus = AsyncEventBus()
        bus.register(OrderConfirmed, NotifyWarehouse())  # async handler
        bus.register(OrderConfirmed, WriteAuditLine())  # sync handler
        await bus.publish(*order.pull_pending_events())

    Handlers for one event run in order, not concurrently: an event's
    consequences are usually easier to reason about — and to log — sequentially.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[SafeAsyncEventHandler]] = (
            defaultdict(list)
        )

    def register(
        self, event_type: type[DomainEvent], handler: EventHandler | AsyncEventHandler
    ) -> None:
        """Register a handler for an event type (multiple handlers allowed)."""
        self._handlers[event_type].append(SafeAsyncEventHandler(handler))

    def register_all(self, handlers: AnyHandlerMapping) -> None:
        """Register several handlers from a mapping or an iterable of pairs."""
        pairs: Iterable[tuple[type[DomainEvent], EventHandler | AsyncEventHandler]]
        if isinstance(handlers, Mapping):
            pairs = cast(
                "Iterable[tuple[type[DomainEvent], EventHandler | AsyncEventHandler]]",
                handlers.items(),
            )
        else:
            pairs = handlers
        for event_type, handler in pairs:
            self.register(event_type, handler)

    async def publish(self, *events: DomainEvent) -> None:
        """Dispatch each event to every handler registered for its type."""
        for event in events:
            for handler in self._handlers.get(type(event), ()):
                await handler.handle(event)

    def clear(self) -> None:
        """Remove all registered handlers."""
        self._handlers.clear()

    def handler_count(self, event_type: type[DomainEvent] | None = None) -> int:
        """Number of handlers registered, for one event type or in total."""
        if event_type is None:
            return sum(len(handlers) for handlers in self._handlers.values())
        return len(self._handlers.get(event_type, ()))
