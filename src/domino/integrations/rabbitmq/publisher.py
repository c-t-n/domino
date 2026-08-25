"""Publish domain events to a RabbitMQ exchange.

RabbitMQ gives what a stream does not: routing by pattern, per-consumer queues,
retries and a dead-letter path — the fit when services need the *broker* to
decide who gets what::

    connection = await aio_pika.connect_robust("amqp://…")
    channel = await connection.channel()
    exchange = await declare_event_exchange(channel)

    publisher = AsyncRabbitMQPublisher(exchange, registry)
    await publisher.publish(*order.pull_pending_events())

Only an async publisher is provided: ``aio-pika`` is an async client, and the
sync alternative is a different library altogether. A synchronous application
can still drive it through ``AsyncOutboxRelay``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractExchange

from domino.events.domain_event import DomainEvent
from domino.events.publisher import AsyncEventPublisher
from domino.events.serialization import EventRegistry

RoutingKeySelector = str | Callable[[DomainEvent], str]


def event_name_routing_key(event: DomainEvent) -> str:
    """Route on the event's name — ``OrderConfirmed``, and so on."""
    return event.event_name


class AsyncRabbitMQPublisher(AsyncEventPublisher):
    """Publishes each event to an exchange, as a persistent JSON message.

    The body is the full
    :class:`~domino.events.serialization.EventRegistry` envelope. The AMQP
    properties mirror its identity — ``message_id``, ``correlation_id``, ``type``
    — so a non-Domino consumer, a management UI or a tracing tool can read them
    without parsing the body, while the body stays the single source of truth.

    Args:
        exchange: the exchange to publish to, from
            :func:`~domino.integrations.rabbitmq.topology.declare_event_exchange`.
        registry: encodes the events — every published type must be registered.
        routing_key: a fixed key, or a callable per event (the event's name by
            default).
        persistent: keep messages across a broker restart. Turning this off
            trades durability for throughput, and is rarely what you want for
            domain events.
    """

    def __init__(
        self,
        exchange: AbstractExchange,
        registry: EventRegistry,
        *,
        routing_key: RoutingKeySelector = event_name_routing_key,
        persistent: bool = True,
    ) -> None:
        self._exchange = exchange
        self._registry = registry
        self._routing_key = routing_key
        self._delivery_mode = (
            DeliveryMode.PERSISTENT if persistent else DeliveryMode.NOT_PERSISTENT
        )

    def routing_key_for(self, event: DomainEvent) -> str:
        """The routing key an event is published under."""
        if isinstance(self._routing_key, str):
            return self._routing_key
        return self._routing_key(event)

    def message_for(self, event: DomainEvent) -> Message:
        """The AMQP message carrying an event."""
        envelope = self._registry.encode(event)
        headers: dict[str, Any] = {"occurred_on": envelope["occurred_on"]}
        return Message(
            body=json.dumps(envelope).encode(),
            content_type="application/json",
            content_encoding="utf-8",
            message_id=envelope["event_id"],
            correlation_id=envelope["correlation_id"],
            type=envelope["event_name"],
            timestamp=event.occurred_on,
            headers=headers,
            delivery_mode=self._delivery_mode,
        )

    async def publish(self, *events: DomainEvent) -> None:
        """Publish the events to the exchange, in order."""
        for event in events:
            await self._exchange.publish(
                self.message_for(event), routing_key=self.routing_key_for(event)
            )
