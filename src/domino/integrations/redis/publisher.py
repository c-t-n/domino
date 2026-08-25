"""Publish domain events to Redis Streams.

A stream is an append-only log with consumer groups: several services read the
same events at their own pace, and a crashed consumer picks up where it left
off. That makes it the lightest broker that still gives real delivery
guarantees::

    from redis.asyncio import Redis
    from domino.integrations.redis import AsyncRedisStreamPublisher

    publisher = AsyncRedisStreamPublisher(Redis(), registry)
    await publisher.publish(*order.pull_pending_events())

Pair it with the [outbox](../sqlalchemy/outbox.py) so an event reaches the
stream even if the process dies right after the commit.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from domino.events.domain_event import DomainEvent
from domino.events.publisher import AsyncEventPublisher, EventPublisher
from domino.events.serialization import EventRegistry
from domino.integrations.redis.message import to_fields

#: Where events land when no stream is configured.
DEFAULT_STREAM = "domino:events"

StreamSelector = str | Callable[[DomainEvent], str]


class _StreamWriter:
    """Shared configuration for the sync and async publishers."""

    def __init__(
        self,
        registry: EventRegistry,
        stream: StreamSelector,
        maxlen: int | None,
        approximate: bool,
    ) -> None:
        self._registry = registry
        self._stream = stream
        self._maxlen = maxlen
        self._approximate = approximate

    def stream_for(self, event: DomainEvent) -> str:
        """The stream an event belongs to."""
        if isinstance(self._stream, str):
            return self._stream
        return self._stream(event)

    def fields_for(self, event: DomainEvent) -> dict[str, str]:
        return to_fields(self._registry, event)

    @property
    def trim(self) -> dict[str, Any]:
        """XADD trimming arguments, if a cap was configured."""
        if self._maxlen is None:
            return {}
        return {"maxlen": self._maxlen, "approximate": self._approximate}


class RedisStreamPublisher(EventPublisher, _StreamWriter):
    """Writes each event to a Redis stream with ``XADD``.

    Args:
        client: a ``redis.Redis``; its ``decode_responses`` setting is yours.
        registry: encodes the events — every published type must be registered.
        stream: a stream name, or a callable routing each event to one (e.g.
            ``lambda event: f"domino:{event.event_name}"``).
        maxlen: cap the stream to roughly this many entries, so a stream nobody
            trims cannot grow without bound. ``approximate`` keeps the trimming
            cheap, which is what you want in production.
    """

    def __init__(
        self,
        client: Any,
        registry: EventRegistry,
        *,
        stream: StreamSelector = DEFAULT_STREAM,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> None:
        _StreamWriter.__init__(self, registry, stream, maxlen, approximate)
        self._client = client

    def publish(self, *events: DomainEvent) -> None:
        """Append the events to their streams, in order."""
        for event in events:
            self._client.xadd(
                self.stream_for(event), self.fields_for(event), **self.trim
            )


class AsyncRedisStreamPublisher(AsyncEventPublisher, _StreamWriter):
    """The ``await``-able twin, over ``redis.asyncio.Redis``."""

    def __init__(
        self,
        client: Any,
        registry: EventRegistry,
        *,
        stream: StreamSelector = DEFAULT_STREAM,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> None:
        _StreamWriter.__init__(self, registry, stream, maxlen, approximate)
        self._client = client

    async def publish(self, *events: DomainEvent) -> None:
        """Append the events to their streams, in order."""
        for event in events:
            await self._client.xadd(
                self.stream_for(event), self.fields_for(event), **self.trim
            )
