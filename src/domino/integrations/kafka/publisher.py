"""Publish domain events to Kafka.

Kafka is a durable, replayable log. Where a queue forgets a message once it is
acknowledged, a Kafka topic keeps it for its retention window, so a new service
can join and read history from the beginning — the reason to reach for it over
Redis Streams or RabbitMQ::

    producer = AIOKafkaProducer(bootstrap_servers="localhost:9092")
    await producer.start()

    publisher = AsyncKafkaPublisher(
        producer, registry, topic="orders", key=aggregate_key("order_id")
    )
    await publisher.publish(*order.pull_pending_events())

**Pick a key.** Kafka guarantees order within a partition, and the key picks the
partition — so keying on the aggregate's id keeps everything that happened to
one order in order, while different orders still spread across the cluster.
Without a key, events are round-robined and that ordering is lost.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from domino.events.domain_event import DomainEvent
from domino.events.publisher import AsyncEventPublisher
from domino.events.serialization import EventRegistry

#: Where events land when no topic is configured.
DEFAULT_TOPIC = "domino.events"

TopicSelector = str | Callable[[DomainEvent], str]
KeySelector = Callable[[DomainEvent], str | None]


def aggregate_key(field: str) -> KeySelector:
    """Key messages on one of the event's fields — the aggregate id, usually.

    ``aggregate_key("order_id")`` sends every event carrying the same
    ``order_id`` to the same partition, which is what keeps their order. An
    event without that field falls back to no key.
    """

    def key_for(event: DomainEvent) -> str | None:
        value = getattr(event, field, None)
        return None if value is None else str(value)

    return key_for


class AsyncKafkaPublisher(AsyncEventPublisher):
    """Sends each event to a topic, as a JSON message with Kafka headers.

    The value is the whole
    :class:`~domino.events.serialization.EventRegistry` envelope. The headers
    repeat its identity — ``event_name``, ``event_id``, ``correlation_id`` — so a
    consumer, a stream processor or a console tool can filter without parsing
    the value.

    Args:
        producer: a **started** ``AIOKafkaProducer``.
        registry: encodes the events — every published type must be registered.
        topic: a topic name, or a callable routing each event to one.
        key: what to partition on; see :func:`aggregate_key`. ``None`` publishes
            without a key, which spreads events round-robin and gives up
            per-aggregate ordering.
    """

    def __init__(
        self,
        producer: Any,
        registry: EventRegistry,
        *,
        topic: TopicSelector = DEFAULT_TOPIC,
        key: KeySelector | None = None,
    ) -> None:
        self._producer = producer
        self._registry = registry
        self._topic = topic
        self._key = key

    def topic_for(self, event: DomainEvent) -> str:
        """The topic an event is published to."""
        if isinstance(self._topic, str):
            return self._topic
        return self._topic(event)

    def key_for(self, event: DomainEvent) -> bytes | None:
        """The partition key for an event, if one was configured."""
        if self._key is None:
            return None
        key = self._key(event)
        return None if key is None else key.encode()

    def record_for(self, event: DomainEvent) -> tuple[bytes, list[tuple[str, bytes]]]:
        """The value and headers carrying an event."""
        envelope = self._registry.encode(event)
        headers = [
            ("event_name", envelope["event_name"].encode()),
            ("event_id", envelope["event_id"].encode()),
            ("correlation_id", (envelope["correlation_id"] or "").encode()),
        ]
        return json.dumps(envelope).encode(), headers

    async def publish(self, *events: DomainEvent) -> None:
        """Send the events, waiting for the broker to acknowledge each one.

        ``send_and_wait`` rather than fire-and-forget: an outbox relay must not
        mark a line published before the broker has it.
        """
        for event in events:
            value, headers = self.record_for(event)
            await self._producer.send_and_wait(
                self.topic_for(event),
                value=value,
                key=self.key_for(event),
                headers=headers,
            )
