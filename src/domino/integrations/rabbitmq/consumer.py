"""Consume domain events from a RabbitMQ queue, into a local event bus.

Several instances of a service consume the *same* queue and RabbitMQ shares the
messages between them — competing consumers, with no group to configure. Give
each service its own queue, bound to the shared exchange, and every service sees
the events it asked for::

    queue = await declare_event_queue(
        channel, "warehouse", exchange=exchange, routing_keys=["OrderConfirmed"]
    )
    consumer = AsyncRabbitMQConsumer(queue, registry, bus=bus)
    await consumer.run()

Each message reopens the producer's
:func:`~domino.core.correlation.correlation_scope`, so one trace spans the
services.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from aio_pika.abc import AbstractIncomingMessage, AbstractQueue

from domino.core.correlation import correlation_scope
from domino.core.logging import get_logger
from domino.events.bus import AsyncEventBus
from domino.events.serialization import EventRegistry, SerializationError

#: ``async def seen(event_id) -> bool`` — True when the event was handled before.
Deduplicator = Callable[[str], Awaitable[bool]]

_logger = get_logger("RabbitMQConsumer")


class AsyncRabbitMQConsumer:
    """Reads a queue and dispatches each message to a local event bus.

    A message is acknowledged **after** the bus has dispatched it, so a consumer
    killed mid-message leaves it on the queue for another instance.

    One it cannot decode — an unregistered event type, a malformed body — is
    rejected without requeue, which sends it to the queue's dead-letter exchange
    when :func:`~domino.integrations.rabbitmq.topology.declare_event_queue`
    declared one. Requeueing instead would spin the same broken message forever.

    Args:
        queue: the queue to consume, already declared and bound.
        registry: rebuilds events — the types must be registered on this side too.
        bus: where decoded events are dispatched.
        deduplicator: optional ``async (event_id) -> bool`` returning True when
            the event was already handled. Delivery is at-least-once, so a
            handler that is not idempotent needs one — a Redis ``SET NX EX``
            makes a good ledger.
    """

    def __init__(
        self,
        queue: AbstractQueue,
        registry: EventRegistry,
        *,
        bus: AsyncEventBus,
        deduplicator: Deduplicator | None = None,
    ) -> None:
        self._queue = queue
        self._registry = registry
        self._bus = bus
        self._deduplicator = deduplicator

    async def run_once(self, max_messages: int = 10) -> int:
        """Handle up to ``max_messages`` waiting messages; returns how many.

        Returns as soon as the queue is empty, which makes it the shape to call
        from a scheduler — or from a test.
        """
        handled = 0
        for _ in range(max_messages):
            message = await self._queue.get(fail=False)
            if message is None:
                break
            if await self._handle(message):
                handled += 1
        return handled

    async def run(self) -> None:
        """Consume until cancelled, one message at a time."""
        async with self._queue.iterator() as messages:
            async for message in messages:
                await self._handle(message)

    async def _handle(self, message: AbstractIncomingMessage) -> bool:
        """Dispatch one message; returns True when it reached the bus."""
        try:
            envelope = _envelope_from(message)
            event = self._registry.decode(envelope)
        except (SerializationError, json.JSONDecodeError) as error:
            _logger.error(
                "cannot decode message %s, dead-lettering it: %s",
                message.message_id,
                error,
            )
            await message.reject(requeue=False)
            return False

        event_id = envelope.get("event_id")
        if (
            self._deduplicator is not None
            and event_id
            and await self._deduplicator(event_id)
        ):
            await message.ack()
            return False

        with correlation_scope(envelope.get("correlation_id")):
            await self._bus.publish(event)
        await message.ack()
        return True


def _envelope_from(message: AbstractIncomingMessage) -> dict[str, Any]:
    """The envelope carried by a message body."""
    try:
        envelope = json.loads(message.body)
    except json.JSONDecodeError as exc:
        raise SerializationError(f"message body is not JSON: {exc}") from exc
    if not isinstance(envelope, dict):
        raise SerializationError("message body must be a JSON object")
    return envelope
