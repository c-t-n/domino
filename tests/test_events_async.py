"""Tests for the async event port, bus and handlers."""

from __future__ import annotations

import logging

import pytest

from domino.events.bus import AsyncEventBus, EventBus
from domino.events.domain_event import DomainEvent
from domino.events.handler import (
    AsyncEventHandler,
    EventHandler,
    SafeAsyncEventHandler,
)
from domino.events.publisher import AsyncEventPublisher
from domino.uow.unit_of_work import AsyncUnitOfWork


class Confirmed(DomainEvent):
    label: str = ""


class Shipped(DomainEvent):
    label: str = ""


class RecordingAsyncHandler(AsyncEventHandler):
    def __init__(self) -> None:
        self.seen: list[DomainEvent] = []

    async def handle(self, event: DomainEvent) -> None:
        self.seen.append(event)


class RecordingSyncHandler(EventHandler):
    def __init__(self) -> None:
        self.seen: list[DomainEvent] = []

    def handle(self, event: DomainEvent) -> None:
        self.seen.append(event)


class ExplodingAsyncHandler(AsyncEventHandler):
    async def handle(self, event: DomainEvent) -> None:
        raise RuntimeError("boom")


class RecordingAsyncPublisher(AsyncEventPublisher):
    """A stand-in for a broker client."""

    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    async def publish(self, *events: DomainEvent) -> None:
        self.published.extend(events)


class TestAsyncEventBus:
    async def test_dispatches_to_an_async_handler(self):
        bus, handler = AsyncEventBus(), RecordingAsyncHandler()
        bus.register(Confirmed, handler)
        event = Confirmed(label="a")

        await bus.publish(event)

        assert handler.seen == [event]

    async def test_dispatches_to_a_sync_handler_too(self):
        bus, handler = AsyncEventBus(), RecordingSyncHandler()
        bus.register(Confirmed, handler)

        await bus.publish(Confirmed(label="a"))

        assert len(handler.seen) == 1

    async def test_routes_by_event_type(self):
        bus = AsyncEventBus()
        confirmed, shipped = RecordingAsyncHandler(), RecordingAsyncHandler()
        bus.register_all([(Confirmed, confirmed), (Shipped, shipped)])

        await bus.publish(Confirmed(), Shipped(), Shipped())

        assert len(confirmed.seen) == 1
        assert len(shipped.seen) == 2

    async def test_many_handlers_run_in_registration_order(self):
        bus = AsyncEventBus()
        order: list[str] = []

        class Named(AsyncEventHandler):
            def __init__(self, name: str) -> None:
                self.name = name

            async def handle(self, event: DomainEvent) -> None:
                order.append(self.name)

        bus.register(Confirmed, Named("first"))
        bus.register(Confirmed, Named("second"))
        await bus.publish(Confirmed())

        assert order == ["first", "second"]

    async def test_a_failing_handler_is_isolated(self, caplog):
        bus, survivor = AsyncEventBus(), RecordingAsyncHandler()
        bus.register(Confirmed, ExplodingAsyncHandler())
        bus.register(Confirmed, survivor)

        with caplog.at_level(logging.ERROR, logger="domino"):
            await bus.publish(Confirmed())  # must not raise

        assert len(survivor.seen) == 1  # the next handler still ran
        assert "boom" in caplog.text

    async def test_unregistered_event_is_a_noop(self):
        await AsyncEventBus().publish(Confirmed())

    def test_handler_count_and_clear(self):
        bus = AsyncEventBus()
        bus.register(Confirmed, RecordingAsyncHandler())
        bus.register(Confirmed, RecordingSyncHandler())
        bus.register(Shipped, RecordingAsyncHandler())

        assert bus.handler_count(Confirmed) == 2
        assert bus.handler_count() == 3
        bus.clear()
        assert bus.handler_count() == 0


class TestSafeAsyncEventHandler:
    async def test_calls_an_error_callback_instead_of_raising(self):
        seen: list[tuple[DomainEvent, Exception]] = []
        handler = SafeAsyncEventHandler(
            ExplodingAsyncHandler(), on_error=lambda e, err: seen.append((e, err))
        )

        await handler.handle(Confirmed())

        assert len(seen) == 1
        assert isinstance(seen[0][1], RuntimeError)


class TestAsyncUnitOfWorkPublishing:
    async def test_awaits_an_async_publisher(self):
        publisher = RecordingAsyncPublisher()
        uow = AsyncUnitOfWork(event_bus=publisher)
        event = Confirmed(label="a")

        async with uow:
            uow.enqueue_events(event)

        assert publisher.published == [event]

    async def test_still_accepts_a_sync_publisher(self):
        # The in-memory EventBus is synchronous; it must keep working under an
        # async unit of work, which is what tests and simple apps rely on.
        bus, handler = EventBus(), RecordingSyncHandler()
        bus.register(Confirmed, handler)
        uow = AsyncUnitOfWork(event_bus=bus)

        async with uow:
            uow.enqueue_events(Confirmed())

        assert len(handler.seen) == 1

    async def test_drives_an_async_bus_end_to_end(self):
        bus, handler = AsyncEventBus(), RecordingAsyncHandler()
        bus.register(Confirmed, handler)
        uow = AsyncUnitOfWork(event_bus=bus)

        async with uow:
            uow.enqueue_events(Confirmed())

        assert len(handler.seen) == 1

    async def test_nothing_is_published_before_the_commit(self):
        publisher = RecordingAsyncPublisher()
        uow = AsyncUnitOfWork(event_bus=publisher)

        async with uow:
            uow.enqueue_events(Confirmed())
            assert publisher.published == []

        assert len(publisher.published) == 1

    async def test_rollback_drops_the_queue(self):
        publisher = RecordingAsyncPublisher()
        uow = AsyncUnitOfWork(event_bus=publisher)

        with pytest.raises(ValueError):
            async with uow:
                uow.enqueue_events(Confirmed())
                raise ValueError("boom")

        assert publisher.published == []
