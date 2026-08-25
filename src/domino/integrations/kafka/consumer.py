"""Consume domain events from Kafka, into a local event bus.

A consumer group shares a topic's partitions between its members, and the
committed **offset** is what a group remembers: it is Kafka's acknowledgement,
so nothing is deleted when you consume — the log is still there for another
group, or for this one after a reset::

    consumer = AIOKafkaConsumer(
        "orders",
        bootstrap_servers="localhost:9092",
        group_id="warehouse",
        enable_auto_commit=False,   # Domino commits after dispatching
        auto_offset_reset="earliest",
    )
    await consumer.start()

    await AsyncKafkaConsumer(consumer, registry, bus=bus).run()

Always disable auto-commit. Left on, Kafka commits on a timer whether or not
your handlers ran, and a crash then skips events nobody handled.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from domino.core.correlation import correlation_scope
from domino.core.logging import get_logger
from domino.events.bus import AsyncEventBus
from domino.events.serialization import EventRegistry, SerializationError

#: ``async def seen(event_id) -> bool`` — True when the event was handled before.
Deduplicator = Callable[[str], Awaitable[bool]]

_logger = get_logger("KafkaConsumer")


class AsyncKafkaConsumer:
    """Reads records into an event bus, committing offsets after dispatch.

    Args:
        consumer: a **started** ``AIOKafkaConsumer``, subscribed and configured
            with ``enable_auto_commit=False``.
        registry: rebuilds events — the types must be registered on this side too.
        bus: where decoded events are dispatched.
        deduplicator: optional ``async (event_id) -> bool``. Committing happens
            after a batch, so a crash mid-batch replays it; a handler that is not
            idempotent needs this.
        dead_letter_producer: a started ``AIOKafkaProducer`` to forward records
            this consumer cannot decode.
        dead_letter_topic: where to forward them.

    Without a dead-letter topic, an undecodable record is logged and skipped —
    Kafka has no queue to leave it in, and refusing to commit would stall the
    partition on the same poison record forever.
    """

    def __init__(
        self,
        consumer: Any,
        registry: EventRegistry,
        *,
        bus: AsyncEventBus,
        deduplicator: Deduplicator | None = None,
        dead_letter_producer: Any | None = None,
        dead_letter_topic: str | None = None,
    ) -> None:
        if bool(dead_letter_producer) != bool(dead_letter_topic):
            raise ValueError(
                "pass both dead_letter_producer and dead_letter_topic, or neither"
            )
        self._consumer = consumer
        self._registry = registry
        self._bus = bus
        self._deduplicator = deduplicator
        self._dead_letter_producer = dead_letter_producer
        self._dead_letter_topic = dead_letter_topic

    async def run_once(self, timeout_ms: int = 1000, max_records: int = 100) -> int:
        """Handle one poll's worth of records, then commit; returns how many.

        Returns 0 when the poll times out with nothing to read, which makes it
        the shape to call from a scheduler — or from a test.
        """
        batch = await self._consumer.getmany(
            timeout_ms=timeout_ms, max_records=max_records
        )
        handled = 0
        for records in batch.values():
            for record in records:
                if await self._handle(record):
                    handled += 1
        if any(batch.values()):
            await self._consumer.commit()
        return handled

    async def run(self) -> None:
        """Consume until cancelled, committing after each record."""
        async for record in self._consumer:
            await self._handle(record)
            await self._consumer.commit()

    async def _handle(self, record: Any) -> bool:
        """Dispatch one record; returns True when it reached the bus."""
        try:
            envelope = _envelope_from(record)
            event = self._registry.decode(envelope)
        except (SerializationError, json.JSONDecodeError) as error:
            await self._dead_letter(record, error)
            return False

        event_id = envelope.get("event_id")
        if (
            self._deduplicator is not None
            and event_id
            and await self._deduplicator(event_id)
        ):
            return False

        with correlation_scope(envelope.get("correlation_id")):
            await self._bus.publish(event)
        return True

    async def _dead_letter(self, record: Any, error: Exception) -> None:
        """Forward what cannot be decoded, or say plainly that it was dropped."""
        if self._dead_letter_producer is None:
            _logger.error(
                "cannot decode %s[%s]@%s, skipping it (no dead_letter_topic): %s",
                record.topic,
                record.partition,
                record.offset,
                error,
            )
            return
        _logger.error(
            "cannot decode %s[%s]@%s, forwarding to %s: %s",
            record.topic,
            record.partition,
            record.offset,
            self._dead_letter_topic,
            error,
        )
        await self._dead_letter_producer.send_and_wait(
            self._dead_letter_topic,
            value=record.value,
            key=record.key,
            headers=list(record.headers or ()),
        )


def _envelope_from(record: Any) -> dict[str, Any]:
    """The envelope carried by a record's value."""
    try:
        envelope = json.loads(record.value)
    except json.JSONDecodeError as exc:
        raise SerializationError(f"record value is not JSON: {exc}") from exc
    if not isinstance(envelope, dict):
        raise SerializationError("record value must be a JSON object")
    return envelope
