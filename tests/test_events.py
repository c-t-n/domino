"""Tests for DomainEvent, EventHandler, SafeEventHandler and EventBus."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
from uuid import UUID

import pytest

from domino.core.id import DomainId
from domino.events.bus import EventBus
from domino.events.domain_event import DomainEvent
from domino.events.handler import EventHandler, SafeEventHandler


class OrderCreated(DomainEvent):
    order_id: DomainId
    total: str


class OrderShipped(DomainEvent):
    order_id: DomainId
    tracking_number: str | None = None


class Recorder(EventHandler):
    """Records the events it receives (regardless of type)."""

    def __init__(self) -> None:
        self.handled: list[DomainEvent] = []

    def handle(self, event: DomainEvent) -> None:
        self.handled.append(event)


class TestDomainEvent:
    def test_event_name(self):
        event = OrderCreated(order_id=DomainId.generate(), total="100.00")
        assert event.event_name == "OrderCreated"

    def test_id_and_timestamp_are_auto_filled(self):
        event = OrderCreated(order_id=DomainId.generate(), total="100.00")
        assert isinstance(event.event_id, UUID)
        assert isinstance(event.occurred_on, datetime)

    def test_events_get_distinct_ids(self):
        a = OrderCreated(order_id=DomainId.generate(), total="1")
        b = OrderCreated(order_id=DomainId.generate(), total="1")
        assert a.event_id != b.event_id

    def test_events_are_immutable(self):
        event = OrderShipped(order_id=DomainId.generate())
        with pytest.raises(FrozenInstanceError):
            event.tracking_number = "TRK-1"  # ty: ignore[invalid-assignment]


class TestEventBus:
    def test_register_and_publish(self):
        bus = EventBus()
        handler = Recorder()
        bus.register(OrderCreated, handler)

        order_id = DomainId.generate()
        bus.publish(OrderCreated(order_id=order_id, total="100.00"))

        assert len(handler.handled) == 1
        published = handler.handled[0]
        assert isinstance(published, OrderCreated)
        assert published.order_id == order_id

    def test_many_handlers_for_one_event(self):
        bus = EventBus()
        a, b = Recorder(), Recorder()
        bus.register(OrderCreated, a)
        bus.register(OrderCreated, b)

        bus.publish(OrderCreated(order_id=DomainId.generate(), total="1"))

        assert len(a.handled) == 1
        assert len(b.handled) == 1

    def test_routes_by_event_type(self):
        bus = EventBus()
        created, shipped = Recorder(), Recorder()
        bus.register(OrderCreated, created)
        bus.register(OrderShipped, shipped)

        bus.publish(
            OrderCreated(order_id=DomainId.generate(), total="50.00"),
            OrderShipped(order_id=DomainId.generate(), tracking_number="TRK-123"),
        )

        assert len(created.handled) == 1
        assert len(shipped.handled) == 1

    def test_register_all_from_pairs(self):
        bus = EventBus()
        inventory, email = Recorder(), Recorder()
        bus.register_all([(OrderCreated, inventory), (OrderCreated, email)])

        bus.publish(OrderCreated(order_id=DomainId.generate(), total="1"))

        assert len(inventory.handled) == 1
        assert len(email.handled) == 1

    def test_register_all_from_mapping(self):
        bus = EventBus()
        created, shipped = Recorder(), Recorder()
        bus.register_all({OrderCreated: created, OrderShipped: shipped})

        bus.publish(
            OrderCreated(order_id=DomainId.generate(), total="1"),
            OrderShipped(order_id=DomainId.generate()),
        )

        assert len(created.handled) == 1
        assert len(shipped.handled) == 1

    def test_handler_count(self):
        bus = EventBus()
        assert bus.handler_count() == 0
        bus.register(OrderCreated, Recorder())
        assert bus.handler_count(OrderCreated) == 1
        assert bus.handler_count(OrderShipped) == 0
        assert bus.handler_count() == 1

    def test_clear(self):
        bus = EventBus()
        bus.register(OrderCreated, Recorder())
        bus.clear()
        assert bus.handler_count() == 0

    def test_publish_without_handler_is_noop(self):
        EventBus().publish(OrderShipped(order_id=DomainId.generate()))

    def test_failing_handler_does_not_break_publish(self):
        class Failing(EventHandler):
            def handle(self, event: DomainEvent) -> None:
                raise RuntimeError("intentional failure")

        bus = EventBus()
        survivor = Recorder()
        bus.register(OrderCreated, Failing())
        bus.register(OrderCreated, survivor)

        bus.publish(OrderCreated(order_id=DomainId.generate(), total="1"))

        assert len(survivor.handled) == 1  # the failure was isolated


class TestSafeEventHandler:
    def test_forwards_to_wrapped_handler(self):
        recorder = Recorder()
        SafeEventHandler(recorder).handle(
            OrderCreated(order_id=DomainId.generate(), total="1")
        )
        assert len(recorder.handled) == 1

    def test_catches_errors_and_calls_on_error(self):
        class Failing(EventHandler):
            def handle(self, event: DomainEvent) -> None:
                raise RuntimeError("boom")

        errors: list[Exception] = []
        handler = SafeEventHandler(
            Failing(), on_error=lambda _event, err: errors.append(err)
        )
        handler.handle(OrderCreated(order_id=DomainId.generate(), total="1"))

        assert len(errors) == 1
        assert isinstance(errors[0], RuntimeError)
