"""Tests for the optional RabbitMQ integration (domino.integrations.rabbitmq).

There is no faithful in-memory RabbitMQ, so these drive the integration through
doubles that mimic the aio-pika surface it touches — while building *real*
``aio_pika.Message`` objects, so the wire format is genuinely exercised. The
AMQP protocol itself (bindings, dead-lettering, redelivery) is covered by the
opt-in test at the bottom, which needs a live broker.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import field
from typing import Any, cast

import pytest

pytest.importorskip("aio_pika")

from aio_pika import DeliveryMode, Message

from domino import (
    AggregateRoot,
    AsyncEventBus,
    AsyncEventHandler,
    DomainEvent,
    DomainId,
    EventRegistry,
)
from domino.core.correlation import correlation_scope, get_correlation_id
from domino.integrations.rabbitmq import (
    AsyncRabbitMQConsumer,
    AsyncRabbitMQPublisher,
)

# --- Domain -----------------------------------------------------------------


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    total: str


class OrderShipped(DomainEvent):
    order_id: DomainId


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)


@pytest.fixture
def registry() -> EventRegistry:
    r = EventRegistry()
    r.register_all([OrderConfirmed, OrderShipped])
    return r


def _confirmed(total: str = "42.00") -> OrderConfirmed:
    return OrderConfirmed(order_id=DomainId.generate(), total=total)


# --- Doubles ----------------------------------------------------------------


class FakeExchange:
    """Captures what a publisher sends, as aio-pika's exchange would."""

    def __init__(self) -> None:
        self.published: list[tuple[Message, str]] = []

    async def publish(self, message: Message, routing_key: str, **_: Any) -> None:
        self.published.append((message, routing_key))


class FakeIncomingMessage:
    """One delivery, tracking how the consumer settled it."""

    def __init__(self, message: Message) -> None:
        self.body = message.body
        self.message_id = message.message_id
        self.correlation_id = message.correlation_id
        self.type = message.type
        self.acked = False
        self.rejected: bool | None = None

    async def ack(self) -> None:
        self.acked = True

    async def reject(self, requeue: bool = True) -> None:
        self.rejected = requeue


class FakeQueue:
    """A queue handing out messages one `get` at a time."""

    def __init__(self, messages: list[FakeIncomingMessage] | None = None) -> None:
        self.messages = list(messages or [])
        self.delivered: list[FakeIncomingMessage] = []

    async def get(self, fail: bool = True, **_: Any) -> FakeIncomingMessage | None:
        if not self.messages:
            return None
        message = self.messages.pop(0)
        self.delivered.append(message)
        return message


class Recorder(AsyncEventHandler):
    def __init__(self) -> None:
        self.seen: list[DomainEvent] = []
        self.correlations: list[str | None] = []

    async def handle(self, event: DomainEvent) -> None:
        self.seen.append(event)
        self.correlations.append(get_correlation_id())


def _delivery(publisher: AsyncRabbitMQPublisher, event: DomainEvent):
    """The incoming message a published event becomes."""
    return FakeIncomingMessage(publisher.message_for(event))


# The doubles stand in structurally for aio-pika's exchange and queue without
# subclassing them, so the cast lives here rather than at every call site.
def _publisher(exchange: FakeExchange, registry: EventRegistry, **kw: Any):
    return AsyncRabbitMQPublisher(cast("Any", exchange), registry, **kw)


# --- Publisher --------------------------------------------------------------


class TestPublisher:
    async def test_publishes_one_message_per_event(self, registry):
        exchange = FakeExchange()
        publisher = _publisher(exchange, registry)

        await publisher.publish(_confirmed(), _confirmed())

        assert len(exchange.published) == 2

    async def test_routing_key_defaults_to_the_event_name(self, registry):
        exchange = FakeExchange()
        publisher = _publisher(exchange, registry)

        await publisher.publish(
            _confirmed(), OrderShipped(order_id=DomainId.generate())
        )

        assert [key for _m, key in exchange.published] == [
            "OrderConfirmed",
            "OrderShipped",
        ]

    async def test_a_fixed_routing_key(self, registry):
        exchange = FakeExchange()
        publisher = _publisher(exchange, registry, routing_key="orders")

        await publisher.publish(_confirmed())

        assert exchange.published[0][1] == "orders"

    async def test_a_callable_routing_key(self, registry):
        exchange = FakeExchange()
        publisher = _publisher(
            exchange, registry, routing_key=lambda e: f"orders.{e.event_name}"
        )

        await publisher.publish(_confirmed())

        assert exchange.published[0][1] == "orders.OrderConfirmed"

    async def test_messages_are_persistent_by_default(self, registry):
        # Without this, a broker restart drops everything still queued.
        exchange = FakeExchange()
        await _publisher(exchange, registry).publish(_confirmed())

        assert exchange.published[0][0].delivery_mode == DeliveryMode.PERSISTENT

    async def test_persistence_can_be_turned_off(self, registry):
        exchange = FakeExchange()
        publisher = _publisher(exchange, registry, persistent=False)

        await publisher.publish(_confirmed())

        assert exchange.published[0][0].delivery_mode == DeliveryMode.NOT_PERSISTENT

    async def test_amqp_properties_mirror_the_envelope(self, registry):
        exchange = FakeExchange()
        publisher = _publisher(exchange, registry)
        with correlation_scope("trace-1"):
            event = _confirmed()
        await publisher.publish(event)

        message, _key = exchange.published[0]
        assert message.message_id == str(event.event_id)
        assert message.correlation_id == "trace-1"
        assert message.type == "OrderConfirmed"
        assert message.content_type == "application/json"

    async def test_the_body_is_the_whole_envelope(self, registry):
        exchange = FakeExchange()
        event = _confirmed("13.50")
        await _publisher(exchange, registry).publish(event)

        envelope = json.loads(exchange.published[0][0].body)
        assert envelope["event_name"] == "OrderConfirmed"
        assert envelope["payload"]["total"] == "13.50"
        # Full precision, unlike the second-resolution AMQP timestamp.
        assert envelope["occurred_on"] == event.occurred_on.isoformat()

    async def test_an_unregistered_event_is_refused(self):
        publisher = _publisher(FakeExchange(), EventRegistry())
        with pytest.raises(Exception, match="not registered"):
            await publisher.publish(_confirmed())


# --- Consumer ---------------------------------------------------------------


class TestConsumer:
    def _consumer(self, queue, registry, bus, **kw):
        return AsyncRabbitMQConsumer(cast("Any", queue), registry, bus=bus, **kw)

    async def test_reads_back_what_was_published(self, registry):
        publisher = _publisher(FakeExchange(), registry)
        event = _confirmed()
        queue = FakeQueue([_delivery(publisher, event)])
        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)

        assert await self._consumer(queue, registry, bus).run_once() == 1
        assert recorder.seen == [event]  # same id, timestamp and payload

    async def test_the_producer_correlation_id_is_reopened(self, registry):
        publisher = _publisher(FakeExchange(), registry)
        with correlation_scope("trace-from-the-api"):
            event = _confirmed()
        queue = FakeQueue([_delivery(publisher, event)])
        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)

        await self._consumer(queue, registry, bus).run_once()

        assert recorder.correlations == ["trace-from-the-api"]
        assert get_correlation_id() is None  # the scope closed behind it

    async def test_a_handled_message_is_acknowledged(self, registry):
        publisher = _publisher(FakeExchange(), registry)
        delivery = _delivery(publisher, _confirmed())
        queue = FakeQueue([delivery])

        await self._consumer(queue, registry, AsyncEventBus()).run_once()

        assert delivery.acked
        assert delivery.rejected is None

    async def test_an_empty_queue_is_a_noop(self, registry):
        assert (
            await self._consumer(FakeQueue(), registry, AsyncEventBus()).run_once() == 0
        )

    async def test_max_messages_limits_a_pass(self, registry):
        publisher = _publisher(FakeExchange(), registry)
        queue = FakeQueue([_delivery(publisher, _confirmed()) for _ in range(3)])
        consumer = self._consumer(queue, registry, AsyncEventBus())

        assert await consumer.run_once(max_messages=2) == 2
        assert await consumer.run_once() == 1

    async def test_an_unregistered_event_is_dead_lettered(self, registry, caplog):
        # The producer knows a type this consumer does not.
        producer_registry = EventRegistry()
        producer_registry.register(OrderShipped)
        publisher = _publisher(FakeExchange(), producer_registry)
        delivery = _delivery(publisher, OrderShipped(order_id=DomainId.generate()))
        queue = FakeQueue([delivery])

        consumer_registry = EventRegistry()  # knows nothing
        with caplog.at_level(logging.ERROR, logger="domino"):
            handled = await self._consumer(
                queue, consumer_registry, AsyncEventBus()
            ).run_once()

        assert handled == 0
        assert delivery.rejected is False  # rejected without requeue
        assert not delivery.acked
        assert "dead-lettering" in caplog.text

    async def test_a_malformed_body_is_dead_lettered(self, registry, caplog):
        delivery = FakeIncomingMessage(Message(b"not json at all"))
        queue = FakeQueue([delivery])

        with caplog.at_level(logging.ERROR, logger="domino"):
            assert (
                await self._consumer(queue, registry, AsyncEventBus()).run_once() == 0
            )

        assert delivery.rejected is False

    async def test_a_failing_handler_still_acknowledges(self, registry):
        # The bus isolates handler failures, so the message is not replayed.
        class Exploding(AsyncEventHandler):
            async def handle(self, event: DomainEvent) -> None:
                raise RuntimeError("handler is broken")

        publisher = _publisher(FakeExchange(), registry)
        delivery = _delivery(publisher, _confirmed())
        bus = AsyncEventBus()
        bus.register(OrderConfirmed, Exploding())

        assert (
            await self._consumer(FakeQueue([delivery]), registry, bus).run_once() == 1
        )
        assert delivery.acked


class TestDeduplication:
    async def test_a_seen_event_is_skipped_but_acknowledged(self, registry):
        seen_ids: set[str] = set()

        async def already_seen(event_id: str) -> bool:
            if event_id in seen_ids:
                return True
            seen_ids.add(event_id)
            return False

        publisher = _publisher(FakeExchange(), registry)
        event = _confirmed()
        queue = FakeQueue([_delivery(publisher, event), _delivery(publisher, event)])
        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)
        consumer = AsyncRabbitMQConsumer(
            cast("Any", queue), registry, bus=bus, deduplicator=already_seen
        )

        assert await consumer.run_once() == 1  # the redelivery is skipped
        assert len(recorder.seen) == 1
        assert all(m.acked for m in queue.delivered)  # both settled, none requeued

    async def test_without_a_deduplicator_duplicates_reach_the_handler(self, registry):
        publisher = _publisher(FakeExchange(), registry)
        event = _confirmed()
        queue = FakeQueue([_delivery(publisher, event), _delivery(publisher, event)])
        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)

        assert (
            await AsyncRabbitMQConsumer(
                cast("Any", queue), registry, bus=bus
            ).run_once()
            == 2
        )
        assert len(recorder.seen) == 2


# --- Against a live broker (opt-in) -----------------------------------------

#: Set it to run the tests below against a live broker; CI does, see ci.yml.
RABBITMQ_URL = os.environ.get("RABBITMQ_URL")


@pytest.mark.integration
@pytest.mark.skipif(not RABBITMQ_URL, reason="set RABBITMQ_URL to run this")
async def test_round_trip_through_a_real_broker(registry):
    """The protocol itself: declare, bind, publish, consume, acknowledge."""
    import aio_pika

    from domino.integrations.rabbitmq import declare_event_exchange, declare_event_queue

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        exchange = await declare_event_exchange(channel, "domino.test")
        queue = await declare_event_queue(
            channel, "domino.test.consumer", exchange=exchange, dead_letter=False
        )
        await queue.purge()

        event = _confirmed()
        await AsyncRabbitMQPublisher(exchange, registry).publish(event)

        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)
        consumer = AsyncRabbitMQConsumer(queue, registry, bus=bus)

        assert await consumer.run_once() == 1
        assert recorder.seen == [event]
        await queue.delete()


@pytest.mark.integration
@pytest.mark.skipif(not RABBITMQ_URL, reason="set RABBITMQ_URL to run this")
async def test_an_undecodable_message_really_reaches_the_dead_letter_queue():
    """What the doubles cannot prove: the broker honours the reject."""
    import aio_pika

    from domino.integrations.rabbitmq import declare_event_exchange, declare_event_queue

    producer_registry = EventRegistry()
    producer_registry.register(OrderShipped)

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        exchange = await declare_event_exchange(channel, "domino.test.dl")
        queue = await declare_event_queue(
            channel, "domino.test.dl.consumer", exchange=exchange
        )
        await queue.purge()

        await AsyncRabbitMQPublisher(exchange, producer_registry).publish(
            OrderShipped(order_id=DomainId.generate())
        )

        consumer_registry = EventRegistry()  # knows nothing of OrderShipped
        consumer = AsyncRabbitMQConsumer(queue, consumer_registry, bus=AsyncEventBus())
        assert await consumer.run_once() == 0

        dead = await channel.get_queue("domino.test.dl.consumer.dead")
        rejected = await dead.get(timeout=5)
        assert rejected is not None
        assert json.loads(rejected.body)["event_name"] == "OrderShipped"
        await rejected.ack()

        await queue.delete()
        await dead.delete()
        await channel.exchange_delete("domino.test.dl")
        await channel.exchange_delete("domino.test.dl.consumer.dlx")
