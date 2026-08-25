"""Tests for the optional Redis Streams integration (domino.integrations.redis)."""

from __future__ import annotations

import logging
from dataclasses import field
from datetime import timedelta
from typing import cast

import pytest

pytest.importorskip("redis")
pytest.importorskip("fakeredis")

import fakeredis
import fakeredis.aioredis

from domino import (
    AggregateRoot,
    AsyncEventBus,
    AsyncEventHandler,
    DomainEvent,
    DomainId,
    EventBus,
    EventHandler,
    EventRegistry,
)
from domino.core.correlation import correlation_scope, get_correlation_id
from domino.integrations.redis import (
    DEFAULT_STREAM,
    AsyncRedisStreamConsumer,
    AsyncRedisStreamPublisher,
    RedisStreamConsumer,
    RedisStreamPublisher,
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


@pytest.fixture
def client():
    return fakeredis.FakeRedis()


@pytest.fixture
def async_client():
    return fakeredis.aioredis.FakeRedis()


# --- Handlers ---------------------------------------------------------------


class Recorder(EventHandler):
    def __init__(self) -> None:
        self.seen: list[DomainEvent] = []
        self.correlations: list[str | None] = []

    def handle(self, event: DomainEvent) -> None:
        self.seen.append(event)
        self.correlations.append(get_correlation_id())


class AsyncRecorder(AsyncEventHandler):
    def __init__(self) -> None:
        self.seen: list[DomainEvent] = []
        self.correlations: list[str | None] = []

    async def handle(self, event: DomainEvent) -> None:
        self.seen.append(event)
        self.correlations.append(get_correlation_id())


def _confirmed(total: str = "42.00") -> OrderConfirmed:
    return OrderConfirmed(order_id=DomainId.generate(), total=total)


class TestPublisher:
    def test_writes_an_entry_per_event(self, client, registry):
        publisher = RedisStreamPublisher(client, registry)

        publisher.publish(_confirmed(), _confirmed())

        assert client.xlen(DEFAULT_STREAM) == 2

    def test_entry_fields_stay_readable(self, client, registry):
        publisher = RedisStreamPublisher(client, registry)
        event = _confirmed("13.50")

        publisher.publish(event)

        (_id, fields) = client.xrange(DEFAULT_STREAM)[0]
        assert fields[b"event_name"] == b"OrderConfirmed"
        assert fields[b"event_id"] == str(event.event_id).encode()
        assert b'"total": "13.50"' in fields[b"payload"]

    def test_routes_by_a_callable(self, client, registry):
        publisher = RedisStreamPublisher(
            client, registry, stream=lambda event: f"domino:{event.event_name}"
        )

        publisher.publish(_confirmed(), OrderShipped(order_id=DomainId.generate()))

        assert client.xlen("domino:OrderConfirmed") == 1
        assert client.xlen("domino:OrderShipped") == 1

    def test_maxlen_caps_the_stream(self, client, registry):
        publisher = RedisStreamPublisher(client, registry, maxlen=2, approximate=False)

        publisher.publish(_confirmed(), _confirmed(), _confirmed())

        assert client.xlen(DEFAULT_STREAM) == 2

    def test_an_unregistered_event_is_refused(self, client):
        publisher = RedisStreamPublisher(client, EventRegistry())
        with pytest.raises(Exception, match="not registered"):
            publisher.publish(_confirmed())

    async def test_async_publisher(self, async_client, registry):
        publisher = AsyncRedisStreamPublisher(async_client, registry)

        await publisher.publish(_confirmed())

        assert await async_client.xlen(DEFAULT_STREAM) == 1

    async def test_a_decoding_client_is_fine_too(self, registry):
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        publisher = AsyncRedisStreamPublisher(client, registry)

        await publisher.publish(_confirmed())

        # redis-py types xrange loosely; an entry is really (id, fields).
        entries = cast(
            "list[tuple[str, dict[str, str]]]", await client.xrange(DEFAULT_STREAM)
        )
        assert entries[0][1]["event_name"] == "OrderConfirmed"


class TestConsumer:
    def _consumer(self, client, registry, bus, **kw):
        consumer = RedisStreamConsumer(
            client, registry, bus=bus, group="g", consumer="c1", block_ms=0, **kw
        )
        consumer.ensure_group()
        return consumer

    def test_reads_back_what_was_published(self, client, registry):
        bus, recorder = EventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)
        consumer = self._consumer(client, registry, bus)
        event = _confirmed()
        RedisStreamPublisher(client, registry).publish(event)

        assert consumer.run_once() == 1
        assert recorder.seen == [event]  # same id, timestamp and payload

    def test_the_producer_correlation_id_is_reopened(self, client, registry):
        # The point of the whole exercise: one trace across two services.
        bus, recorder = EventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)
        consumer = self._consumer(client, registry, bus)
        with correlation_scope("trace-from-the-api"):
            RedisStreamPublisher(client, registry).publish(_confirmed())

        consumer.run_once()

        assert recorder.correlations == ["trace-from-the-api"]
        assert get_correlation_id() is None  # the scope closed behind it

    def test_acknowledged_entries_are_not_redelivered(self, client, registry):
        bus, recorder = EventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)
        consumer = self._consumer(client, registry, bus)
        RedisStreamPublisher(client, registry).publish(_confirmed())

        assert consumer.run_once() == 1
        assert consumer.run_once() == 0
        assert len(recorder.seen) == 1
        assert client.xpending(DEFAULT_STREAM, "g")["pending"] == 0

    def test_an_empty_stream_is_a_noop(self, client, registry):
        assert self._consumer(client, registry, EventBus()).run_once() == 0

    def test_count_limits_a_batch(self, client, registry):
        bus = EventBus()
        consumer = self._consumer(client, registry, bus, count=2)
        publisher = RedisStreamPublisher(client, registry)
        publisher.publish(_confirmed(), _confirmed(), _confirmed())

        assert consumer.run_once() == 2
        assert consumer.run_once() == 1

    def test_events_nobody_registered_stay_pending(self, client, caplog):
        # An entry this consumer cannot decode must be visible, not dropped.
        producer_registry = EventRegistry()
        producer_registry.register(OrderShipped)
        RedisStreamPublisher(client, producer_registry).publish(
            OrderShipped(order_id=DomainId.generate())
        )

        consumer_registry = EventRegistry()  # knows nothing
        consumer = self._consumer(client, consumer_registry, EventBus())

        with caplog.at_level(logging.ERROR, logger="domino"):
            assert consumer.run_once() == 0

        assert "leaving it pending" in caplog.text
        assert client.xpending(DEFAULT_STREAM, "g")["pending"] == 1

    def test_a_failing_handler_does_not_stop_the_batch(self, client, registry):
        class Exploding(EventHandler):
            def handle(self, event: DomainEvent) -> None:
                raise RuntimeError("handler is broken")

        bus, recorder = EventBus(), Recorder()
        bus.register(OrderConfirmed, Exploding())
        bus.register(OrderConfirmed, recorder)
        consumer = self._consumer(client, registry, bus)
        RedisStreamPublisher(client, registry).publish(_confirmed())

        assert consumer.run_once() == 1
        assert len(recorder.seen) == 1

    def test_ensure_group_is_idempotent(self, client, registry):
        self._consumer(client, registry, EventBus())
        self._consumer(client, registry, EventBus())  # BUSYGROUP, swallowed


class TestDeduplication:
    def test_the_same_event_is_handled_once(self, client, registry):
        # At-least-once delivery means a producer may send an event twice.
        bus, recorder = EventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)
        consumer = RedisStreamConsumer(
            client,
            registry,
            bus=bus,
            group="g",
            consumer="c1",
            block_ms=0,
            dedupe_ttl=timedelta(minutes=5),
        )
        consumer.ensure_group()

        event = _confirmed()
        publisher = RedisStreamPublisher(client, registry)
        publisher.publish(event)
        publisher.publish(event)  # a redelivery of the very same event

        assert consumer.run_once() == 1  # the duplicate is skipped
        assert len(recorder.seen) == 1
        assert client.xpending(DEFAULT_STREAM, "g")["pending"] == 0  # both acked

    def test_without_a_ttl_duplicates_reach_the_handler(self, client, registry):
        bus, recorder = EventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)
        consumer = RedisStreamConsumer(
            client, registry, bus=bus, group="g", consumer="c1", block_ms=0
        )
        consumer.ensure_group()

        event = _confirmed()
        publisher = RedisStreamPublisher(client, registry)
        publisher.publish(event)
        publisher.publish(event)

        assert consumer.run_once() == 2
        assert len(recorder.seen) == 2


class TestAsyncConsumer:
    async def _consumer(self, client, registry, bus, **kw):
        consumer = AsyncRedisStreamConsumer(
            client, registry, bus=bus, group="g", consumer="c1", block_ms=0, **kw
        )
        await consumer.ensure_group()
        return consumer

    async def test_reads_back_what_was_published(self, async_client, registry):
        bus, recorder = AsyncEventBus(), AsyncRecorder()
        bus.register(OrderConfirmed, recorder)
        consumer = await self._consumer(async_client, registry, bus)
        event = _confirmed()
        await AsyncRedisStreamPublisher(async_client, registry).publish(event)

        assert await consumer.run_once() == 1
        assert recorder.seen == [event]

    async def test_correlation_and_acknowledgement(self, async_client, registry):
        bus, recorder = AsyncEventBus(), AsyncRecorder()
        bus.register(OrderConfirmed, recorder)
        consumer = await self._consumer(async_client, registry, bus)
        with correlation_scope("trace-async"):
            await AsyncRedisStreamPublisher(async_client, registry).publish(
                _confirmed()
            )

        assert await consumer.run_once() == 1
        assert recorder.correlations == ["trace-async"]
        assert await consumer.run_once() == 0

    async def test_deduplication(self, async_client, registry):
        bus, recorder = AsyncEventBus(), AsyncRecorder()
        bus.register(OrderConfirmed, recorder)
        consumer = await self._consumer(
            async_client, registry, bus, dedupe_ttl=timedelta(minutes=5)
        )
        event = _confirmed()
        publisher = AsyncRedisStreamPublisher(async_client, registry)
        await publisher.publish(event)
        await publisher.publish(event)

        assert await consumer.run_once() == 1
        assert len(recorder.seen) == 1
