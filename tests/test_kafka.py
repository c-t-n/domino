"""Tests for the optional Kafka integration (domino.integrations.kafka).

The unit tests drive the integration through doubles mimicking the aiokafka
surface it touches. The protocol itself — partitioning, consumer groups, offset
commits — is covered by the opt-in tests at the bottom, which run against
Redpanda in CI (see ci.yml) or any broker named by KAFKA_BOOTSTRAP_SERVERS.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import field
from typing import Any

import pytest

pytest.importorskip("aiokafka")

from domino import (
    AggregateRoot,
    AsyncEventBus,
    AsyncEventHandler,
    DomainEvent,
    DomainId,
    EventRegistry,
)
from domino.core.correlation import correlation_scope, get_correlation_id
from domino.integrations.kafka import (
    DEFAULT_TOPIC,
    AsyncKafkaConsumer,
    AsyncKafkaPublisher,
    aggregate_key,
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


def _confirmed(
    total: str = "42.00", order_id: DomainId | None = None
) -> OrderConfirmed:
    return OrderConfirmed(order_id=order_id or DomainId.generate(), total=total)


# --- Doubles ----------------------------------------------------------------


class FakeRecord:
    """One record, as aiokafka hands it over."""

    def __init__(
        self,
        value: bytes,
        headers: list[tuple[str, bytes]] | None = None,
        *,
        key: bytes | None = None,
        topic: str = DEFAULT_TOPIC,
        partition: int = 0,
        offset: int = 0,
    ) -> None:
        self.value = value
        self.key = key
        self.headers = tuple(headers or ())
        self.topic = topic
        self.partition = partition
        self.offset = offset


class FakeProducer:
    """Captures what a publisher sends."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_and_wait(self, topic: str, **kw: Any) -> None:
        self.sent.append({"topic": topic, **kw})


class FakeConsumer:
    """Serves one batch per `getmany`, and counts commits."""

    def __init__(self, batches: list[list[FakeRecord]] | None = None) -> None:
        self.batches = list(batches or [])
        self.commits = 0

    async def getmany(self, timeout_ms: int = 1000, max_records: int = 100) -> dict:
        if not self.batches:
            return {}
        return {"orders-0": self.batches.pop(0)}

    async def commit(self) -> None:
        self.commits += 1


class Recorder(AsyncEventHandler):
    def __init__(self) -> None:
        self.seen: list[DomainEvent] = []
        self.correlations: list[str | None] = []

    async def handle(self, event: DomainEvent) -> None:
        self.seen.append(event)
        self.correlations.append(get_correlation_id())


def _record(
    publisher: AsyncKafkaPublisher, event: DomainEvent, **kw: Any
) -> FakeRecord:
    """The record a published event becomes."""
    value, headers = publisher.record_for(event)
    return FakeRecord(value, headers, key=publisher.key_for(event), **kw)


def _publisher(producer: FakeProducer, registry: EventRegistry, **kw: Any):
    # The doubles stand in structurally for aiokafka's client; the cast lives
    # here rather than at every call site.
    return AsyncKafkaPublisher(producer, registry, **kw)


def _consumer(
    consumer: FakeConsumer, registry: EventRegistry, bus: AsyncEventBus, **kw: Any
):
    return AsyncKafkaConsumer(consumer, registry, bus=bus, **kw)


# --- Publisher ---------------------------------------------------------------


class TestPublisher:
    async def test_sends_one_record_per_event(self, registry):
        producer = FakeProducer()

        await _publisher(producer, registry).publish(_confirmed(), _confirmed())

        assert len(producer.sent) == 2
        assert producer.sent[0]["topic"] == DEFAULT_TOPIC

    async def test_a_fixed_topic(self, registry):
        producer = FakeProducer()

        await _publisher(producer, registry, topic="orders").publish(_confirmed())

        assert producer.sent[0]["topic"] == "orders"

    async def test_a_callable_topic(self, registry):
        producer = FakeProducer()
        publisher = _publisher(
            producer, registry, topic=lambda e: f"domino.{e.event_name}"
        )

        await publisher.publish(
            _confirmed(), OrderShipped(order_id=DomainId.generate())
        )

        assert [s["topic"] for s in producer.sent] == [
            "domino.OrderConfirmed",
            "domino.OrderShipped",
        ]

    async def test_no_key_by_default(self, registry):
        producer = FakeProducer()

        await _publisher(producer, registry).publish(_confirmed())

        assert producer.sent[0]["key"] is None

    async def test_aggregate_key_puts_one_aggregate_on_one_partition(self, registry):
        # The reason to key at all: Kafka only orders within a partition.
        producer = FakeProducer()
        publisher = _publisher(producer, registry, key=aggregate_key("order_id"))
        order_id = DomainId.generate()

        await publisher.publish(
            _confirmed(order_id=order_id), _confirmed(order_id=order_id)
        )

        keys = [s["key"] for s in producer.sent]
        assert keys[0] == str(order_id).encode()
        assert keys[0] == keys[1]

    async def test_different_aggregates_get_different_keys(self, registry):
        producer = FakeProducer()
        publisher = _publisher(producer, registry, key=aggregate_key("order_id"))

        await publisher.publish(_confirmed(), _confirmed())

        assert producer.sent[0]["key"] != producer.sent[1]["key"]

    async def test_aggregate_key_tolerates_a_missing_field(self, registry):
        producer = FakeProducer()
        publisher = _publisher(producer, registry, key=aggregate_key("nope"))

        await publisher.publish(_confirmed())

        assert producer.sent[0]["key"] is None

    async def test_headers_repeat_the_identity(self, registry):
        producer = FakeProducer()
        with correlation_scope("trace-1"):
            event = _confirmed()
        await _publisher(producer, registry).publish(event)

        headers = dict(producer.sent[0]["headers"])
        assert headers["event_name"] == b"OrderConfirmed"
        assert headers["event_id"] == str(event.event_id).encode()
        assert headers["correlation_id"] == b"trace-1"

    async def test_the_value_is_the_whole_envelope(self, registry):
        producer = FakeProducer()
        event = _confirmed("13.50")

        await _publisher(producer, registry).publish(event)

        envelope = json.loads(producer.sent[0]["value"])
        assert envelope["event_name"] == "OrderConfirmed"
        assert envelope["payload"]["total"] == "13.50"
        assert envelope["occurred_on"] == event.occurred_on.isoformat()

    async def test_an_unregistered_event_is_refused(self):
        with pytest.raises(Exception, match="not registered"):
            await _publisher(FakeProducer(), EventRegistry()).publish(_confirmed())


# --- Consumer ----------------------------------------------------------------


class TestConsumer:
    async def test_reads_back_what_was_published(self, registry):
        publisher = _publisher(FakeProducer(), registry)
        event = _confirmed()
        consumer = FakeConsumer([[_record(publisher, event)]])
        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)

        assert await _consumer(consumer, registry, bus).run_once() == 1
        assert recorder.seen == [event]  # same id, timestamp and payload

    async def test_the_producer_correlation_id_is_reopened(self, registry):
        publisher = _publisher(FakeProducer(), registry)
        with correlation_scope("trace-from-the-api"):
            event = _confirmed()
        consumer = FakeConsumer([[_record(publisher, event)]])
        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)

        await _consumer(consumer, registry, bus).run_once()

        assert recorder.correlations == ["trace-from-the-api"]
        assert get_correlation_id() is None  # the scope closed behind it

    async def test_offsets_are_committed_after_the_batch(self, registry):
        publisher = _publisher(FakeProducer(), registry)
        consumer = FakeConsumer([[_record(publisher, _confirmed())]])

        await _consumer(consumer, registry, AsyncEventBus()).run_once()

        assert consumer.commits == 1

    async def test_an_empty_poll_commits_nothing(self, registry):
        # Committing on an empty poll would be a pointless round trip.
        consumer = FakeConsumer()

        assert await _consumer(consumer, registry, AsyncEventBus()).run_once() == 0
        assert consumer.commits == 0

    async def test_a_whole_batch_is_handled(self, registry):
        publisher = _publisher(FakeProducer(), registry)
        records = [_record(publisher, _confirmed(), offset=i) for i in range(3)]
        consumer = FakeConsumer([records])
        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)

        assert await _consumer(consumer, registry, bus).run_once() == 3
        assert len(recorder.seen) == 3
        assert consumer.commits == 1  # one commit for the batch

    async def test_an_unregistered_event_is_skipped_and_reported(
        self, registry, caplog
    ):
        producer_registry = EventRegistry()
        producer_registry.register(OrderShipped)
        publisher = _publisher(FakeProducer(), producer_registry)
        record = _record(publisher, OrderShipped(order_id=DomainId.generate()))
        consumer = FakeConsumer([[record]])

        with caplog.at_level(logging.ERROR, logger="domino"):
            handled = await _consumer(
                consumer, EventRegistry(), AsyncEventBus()
            ).run_once()

        assert handled == 0
        assert "no dead_letter_topic" in caplog.text
        assert consumer.commits == 1  # committed anyway: no poison-pill stall

    async def test_a_malformed_value_is_skipped(self, registry, caplog):
        consumer = FakeConsumer([[FakeRecord(b"not json at all")]])

        with caplog.at_level(logging.ERROR, logger="domino"):
            assert await _consumer(consumer, registry, AsyncEventBus()).run_once() == 0

    async def test_a_failing_handler_does_not_stop_the_batch(self, registry):
        class Exploding(AsyncEventHandler):
            async def handle(self, event: DomainEvent) -> None:
                raise RuntimeError("handler is broken")

        publisher = _publisher(FakeProducer(), registry)
        consumer = FakeConsumer([[_record(publisher, _confirmed())]])
        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, Exploding())
        bus.register(OrderConfirmed, recorder)

        assert await _consumer(consumer, registry, bus).run_once() == 1
        assert len(recorder.seen) == 1


class TestDeadLettering:
    async def test_undecodable_records_are_forwarded(self, registry, caplog):
        producer_registry = EventRegistry()
        producer_registry.register(OrderShipped)
        publisher = _publisher(FakeProducer(), producer_registry)
        record = _record(publisher, OrderShipped(order_id=DomainId.generate()))
        consumer = FakeConsumer([[record]])
        dead_letters = FakeProducer()

        with caplog.at_level(logging.ERROR, logger="domino"):
            await _consumer(
                consumer,
                EventRegistry(),
                AsyncEventBus(),
                dead_letter_producer=dead_letters,
                dead_letter_topic="orders.dead",
            ).run_once()

        assert len(dead_letters.sent) == 1
        assert dead_letters.sent[0]["topic"] == "orders.dead"
        assert dead_letters.sent[0]["value"] == record.value  # forwarded verbatim

    async def test_half_a_configuration_is_refused(self, registry):
        with pytest.raises(ValueError, match="or neither"):
            _consumer(
                FakeConsumer(),
                registry,
                AsyncEventBus(),
                dead_letter_topic="orders.dead",
            )


class TestDeduplication:
    async def test_a_seen_event_is_skipped(self, registry):
        seen_ids: set[str] = set()

        async def already_seen(event_id: str) -> bool:
            if event_id in seen_ids:
                return True
            seen_ids.add(event_id)
            return False

        publisher = _publisher(FakeProducer(), registry)
        event = _confirmed()
        consumer = FakeConsumer(
            [[_record(publisher, event), _record(publisher, event)]]
        )
        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)

        handled = await _consumer(
            consumer, registry, bus, deduplicator=already_seen
        ).run_once()

        assert handled == 1
        assert len(recorder.seen) == 1

    async def test_without_a_deduplicator_duplicates_reach_the_handler(self, registry):
        publisher = _publisher(FakeProducer(), registry)
        event = _confirmed()
        consumer = FakeConsumer(
            [[_record(publisher, event), _record(publisher, event)]]
        )
        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)

        assert await _consumer(consumer, registry, bus).run_once() == 2
        assert len(recorder.seen) == 2


# --- Against a live broker (opt-in) -----------------------------------------

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS")


@pytest.mark.integration
@pytest.mark.skipif(not BOOTSTRAP, reason="set KAFKA_BOOTSTRAP_SERVERS to run this")
async def test_round_trip_through_a_real_broker(registry):
    """The protocol itself: produce, join a group, consume, commit."""
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

    assert BOOTSTRAP  # guaranteed by the skipif above

    topic = f"domino-test-{uuid.uuid4().hex[:8]}"
    producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP)
    await producer.start()
    try:
        with correlation_scope("trace-live"):
            event = _confirmed()
        await AsyncKafkaPublisher(
            producer, registry, topic=topic, key=aggregate_key("order_id")
        ).publish(event)
    finally:
        await producer.stop()

    raw = AIOKafkaConsumer(
        topic,
        bootstrap_servers=BOOTSTRAP,
        group_id=f"g-{uuid.uuid4().hex[:8]}",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await raw.start()
    try:
        bus, recorder = AsyncEventBus(), Recorder()
        bus.register(OrderConfirmed, recorder)
        consumer = AsyncKafkaConsumer(raw, registry, bus=bus)

        assert await consumer.run_once(timeout_ms=10_000) == 1
        assert recorder.seen == [event]
        assert recorder.correlations == ["trace-live"]
    finally:
        await raw.stop()


@pytest.mark.integration
@pytest.mark.skipif(not BOOTSTRAP, reason="set KAFKA_BOOTSTRAP_SERVERS to run this")
async def test_the_key_really_drives_partitioning(registry):
    """What the doubles cannot prove: one aggregate, one partition — in order.

    The topic is created with several partitions on purpose. Auto-created topics
    get exactly one, which would make this assertion pass without the key doing
    anything at all.
    """
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic

    assert BOOTSTRAP  # guaranteed by the skipif above
    topic = f"domino-part-{uuid.uuid4().hex[:8]}"
    partitions = 4

    admin = AIOKafkaAdminClient(bootstrap_servers=BOOTSTRAP)
    await admin.start()
    try:
        await admin.create_topics(
            [NewTopic(topic, num_partitions=partitions, replication_factor=1)]
        )
    finally:
        await admin.close()

    order_id = DomainId.generate()
    producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP)
    await producer.start()
    try:
        publisher = AsyncKafkaPublisher(
            producer, registry, topic=topic, key=aggregate_key("order_id")
        )
        # One aggregate's history…
        await publisher.publish(
            _confirmed(order_id=order_id),
            OrderShipped(order_id=order_id),
            _confirmed(order_id=order_id),
        )
        # …plus enough other aggregates that the key must be spreading them.
        for _ in range(24):
            await publisher.publish(_confirmed())
    finally:
        await producer.stop()

    raw = AIOKafkaConsumer(
        topic,
        bootstrap_servers=BOOTSTRAP,
        group_id=f"g-{uuid.uuid4().hex[:8]}",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await raw.start()
    try:
        batch = await raw.getmany(timeout_ms=10_000)
    finally:
        await raw.stop()

    by_partition = {tp.partition: records for tp, records in batch.items()}
    assert sum(len(r) for r in by_partition.values()) == 27
    assert len(by_partition) > 1, "the key is not spreading events across partitions"

    ours = [
        record
        for records in by_partition.values()
        for record in records
        if record.key == str(order_id).encode()
    ]
    partitions_used = {
        tp.partition
        for tp, records in batch.items()
        if any(r.key == str(order_id).encode() for r in records)
    }
    assert len(partitions_used) == 1  # one aggregate never straddles partitions
    assert [dict(r.headers)["event_name"] for r in ours] == [
        b"OrderConfirmed",
        b"OrderShipped",
        b"OrderConfirmed",
    ]  # and its history stays in the order it happened
