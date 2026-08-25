"""RabbitMQ integration: publish domain events to an exchange, and consume them.

Optional — install with ``pip install pydomino[rabbitmq]``. Domino's core has no
runtime dependencies; importing this subpackage requires ``aio-pika``.

- :func:`declare_event_exchange` / :func:`declare_event_queue` — the topology a
  Domino producer and consumer expect, dead-letter path included;
- :class:`AsyncRabbitMQPublisher` — an
  :class:`~domino.events.publisher.AsyncEventPublisher` writing persistent JSON
  messages, ready to hand to an outbox relay;
- :class:`AsyncRabbitMQConsumer` — a queue read into a local event bus,
  reopening the producer's correlation scope for each message.

Events cross as the envelope of
:class:`~domino.events.serialization.EventRegistry`, so both ends register the
types they exchange.
"""

from domino.integrations.rabbitmq.consumer import AsyncRabbitMQConsumer, Deduplicator
from domino.integrations.rabbitmq.publisher import (
    AsyncRabbitMQPublisher,
    event_name_routing_key,
)
from domino.integrations.rabbitmq.topology import (
    DEFAULT_EXCHANGE,
    declare_event_exchange,
    declare_event_queue,
)

__all__ = [
    "DEFAULT_EXCHANGE",
    "declare_event_exchange",
    "declare_event_queue",
    "AsyncRabbitMQPublisher",
    "event_name_routing_key",
    "AsyncRabbitMQConsumer",
    "Deduplicator",
]
