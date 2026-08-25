"""Consume domain events from a Redis stream, into a local event bus.

The half Domino was missing: publishing existed, consuming did not. A consumer
joins a **group**, so several instances share the load and a crashed one leaves
its unacknowledged entries behind for another to claim::

    consumer = AsyncRedisStreamConsumer(
        Redis(), registry, bus=bus, group="billing", consumer="worker-1"
    )
    await consumer.ensure_group()
    await consumer.run()          # until cancelled

Each message reopens the producer's
:func:`~domino.core.correlation.correlation_scope`, so one trace spans the
services — a log line in the consumer carries the id the request started with.

Delivery is at-least-once, so a handler may see an event twice. Pass
``dedupe_ttl`` to have the consumer skip an ``event_id`` it already processed,
using Redis itself as the ledger.
"""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from typing import Any

from domino.core.correlation import correlation_scope
from domino.core.logging import get_logger
from domino.events.bus import AsyncEventBus, EventBus
from domino.events.serialization import EventRegistry, SerializationError
from domino.integrations.redis.message import to_envelope
from domino.integrations.redis.publisher import DEFAULT_STREAM

#: Key prefix for the deduplication ledger.
DEDUPE_PREFIX = "domino:seen:"

_logger = get_logger("RedisStreamConsumer")


class _Consumer:
    """Configuration and message handling shared by both consumers."""

    def __init__(
        self,
        client: Any,
        registry: EventRegistry,
        *,
        group: str,
        consumer: str,
        stream: str = DEFAULT_STREAM,
        count: int = 10,
        block_ms: int = 5000,
        dedupe_ttl: timedelta | None = None,
    ) -> None:
        self._client = client
        self._registry = registry
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._count = count
        self._block_ms = block_ms
        self._dedupe_ttl = dedupe_ttl

    def _entry_id(self, raw: Any) -> str:
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    def _is_busygroup(self, error: Exception) -> bool:
        return "BUSYGROUP" in str(error)

    def _dedupe_key(self, event_id: str) -> str:
        return f"{DEDUPE_PREFIX}{event_id}"

    def _log_undecodable(self, entry_id: str, error: Exception) -> None:
        # Left unacknowledged on purpose: an entry this consumer cannot read is
        # visible in XPENDING rather than silently dropped. Register the missing
        # event type and reclaim it, or acknowledge it deliberately.
        _logger.error(
            "cannot decode entry %s on %s, leaving it pending: %s",
            entry_id,
            self._stream,
            error,
        )


class RedisStreamConsumer(_Consumer):
    """Reads a stream as part of a consumer group and dispatches to an EventBus."""

    def __init__(
        self, client: Any, registry: EventRegistry, *, bus: EventBus, **kw: Any
    ) -> None:
        super().__init__(client, registry, **kw)
        self._bus = bus

    def ensure_group(self) -> None:
        """Create the consumer group (and the stream) unless they exist."""
        try:
            self._client.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except Exception as error:
            if not self._is_busygroup(error):
                raise

    def run_once(self) -> int:
        """Read one batch and dispatch it; returns how many events were handled."""
        batch = self._client.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: ">"},
            count=self._count,
            block=self._block_ms,
        )
        handled = 0
        for _stream, entries in batch or ():
            for raw_id, fields in entries:
                entry_id = self._entry_id(raw_id)
                try:
                    envelope = to_envelope(fields)
                    event = self._registry.decode(envelope)
                except SerializationError as error:
                    self._log_undecodable(entry_id, error)
                    continue

                if self._already_seen(envelope["event_id"]):
                    self._client.xack(self._stream, self._group, entry_id)
                    continue

                with correlation_scope(envelope["correlation_id"]):
                    self._bus.publish(event)
                self._client.xack(self._stream, self._group, entry_id)
                handled += 1
        return handled

    def run(self, idle_sleep: float = 0.0) -> None:
        """Consume forever (Ctrl-C to stop); the read already blocks server-side."""
        while True:
            if self.run_once() == 0 and idle_sleep:
                time.sleep(idle_sleep)

    def _already_seen(self, event_id: str | None) -> bool:
        if self._dedupe_ttl is None or event_id is None:
            return False
        first_time = self._client.set(
            self._dedupe_key(event_id), "1", nx=True, ex=self._dedupe_ttl
        )
        return not first_time


class AsyncRedisStreamConsumer(_Consumer):
    """The ``await``-able twin, over ``redis.asyncio.Redis``."""

    def __init__(
        self, client: Any, registry: EventRegistry, *, bus: AsyncEventBus, **kw: Any
    ) -> None:
        super().__init__(client, registry, **kw)
        self._bus = bus

    async def ensure_group(self) -> None:
        """Create the consumer group (and the stream) unless they exist."""
        try:
            await self._client.xgroup_create(
                self._stream, self._group, id="0", mkstream=True
            )
        except Exception as error:
            if not self._is_busygroup(error):
                raise

    async def run_once(self) -> int:
        """Read one batch and dispatch it; returns how many events were handled."""
        batch = await self._client.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: ">"},
            count=self._count,
            block=self._block_ms,
        )
        handled = 0
        for _stream, entries in batch or ():
            for raw_id, fields in entries:
                entry_id = self._entry_id(raw_id)
                try:
                    envelope = to_envelope(fields)
                    event = self._registry.decode(envelope)
                except SerializationError as error:
                    self._log_undecodable(entry_id, error)
                    continue

                if await self._already_seen(envelope["event_id"]):
                    await self._client.xack(self._stream, self._group, entry_id)
                    continue

                with correlation_scope(envelope["correlation_id"]):
                    await self._bus.publish(event)
                await self._client.xack(self._stream, self._group, entry_id)
                handled += 1
        return handled

    async def run(self, idle_sleep: float = 0.0) -> None:
        """Consume until cancelled; the read already blocks server-side."""
        while True:
            if await self.run_once() == 0 and idle_sleep:
                await asyncio.sleep(idle_sleep)

    async def _already_seen(self, event_id: str | None) -> bool:
        if self._dedupe_ttl is None or event_id is None:
            return False
        first_time = await self._client.set(
            self._dedupe_key(event_id), "1", nx=True, ex=self._dedupe_ttl
        )
        return not first_time
