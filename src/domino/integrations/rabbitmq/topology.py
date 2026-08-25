"""Declaring the exchange, the queues and the dead-letter path.

RabbitMQ routes through an **exchange**: a publisher never names a queue, it
publishes with a routing key and the bindings decide who receives what. Each
consuming service therefore owns a durable queue bound to the shared exchange,
and adding a service means adding a binding — not touching the producer.

These helpers declare that topology the way Domino's consumer expects it. You
can declare it yourself, or with your own infrastructure tooling; nothing here
is required.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue

#: Where events are published when no exchange is named.
DEFAULT_EXCHANGE = "domino.events"

#: Suffixes for a queue's dead-letter exchange and queue.
DEAD_LETTER_SUFFIX = ".dlx"
DEAD_QUEUE_SUFFIX = ".dead"


async def declare_event_exchange(
    channel: AbstractChannel, name: str = DEFAULT_EXCHANGE
) -> AbstractExchange:
    """Declare the durable topic exchange events are published to.

    A topic exchange lets a consumer bind to ``OrderConfirmed``, to
    ``Order.*``, or to everything — without the publisher knowing.
    """
    return await channel.declare_exchange(name, ExchangeType.TOPIC, durable=True)


async def declare_event_queue(
    channel: AbstractChannel,
    name: str,
    *,
    exchange: AbstractExchange,
    routing_keys: Iterable[str] = ("#",),
    dead_letter: bool = True,
) -> AbstractQueue:
    """Declare a durable queue for one consuming service, bound to the exchange.

    With ``dead_letter`` (the default), a companion ``<name>.dlx`` exchange and
    ``<name>.dead`` queue are declared and the queue is pointed at them. A
    message the consumer cannot handle then lands somewhere you can inspect,
    rather than being dropped — which is the whole reason to reject it.

    ``routing_keys`` defaults to ``#``: every event on the exchange.
    """
    arguments: dict[str, Any] = {}
    if dead_letter:
        dead_letter_exchange = await channel.declare_exchange(
            f"{name}{DEAD_LETTER_SUFFIX}", ExchangeType.FANOUT, durable=True
        )
        dead_queue = await channel.declare_queue(
            f"{name}{DEAD_QUEUE_SUFFIX}", durable=True
        )
        await dead_queue.bind(dead_letter_exchange)
        arguments["x-dead-letter-exchange"] = dead_letter_exchange.name

    queue = await channel.declare_queue(name, durable=True, arguments=arguments or None)
    for routing_key in routing_keys:
        await queue.bind(exchange, routing_key=routing_key)
    return queue
