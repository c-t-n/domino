"""Kafka integration: publish domain events to a topic, and consume them.

Optional — install with ``pip install pydomino[kafka]``. Domino's core has no
runtime dependencies; importing this subpackage requires ``aiokafka``.

- :class:`AsyncKafkaPublisher` — an
  :class:`~domino.events.publisher.AsyncEventPublisher` sending the envelope as
  a JSON record, ready to hand to an outbox relay;
- :func:`aggregate_key` — partition on an aggregate's id, which is what keeps
  one aggregate's events in order;
- :class:`AsyncKafkaConsumer` — records read into a local event bus, reopening
  the producer's correlation scope and committing offsets after dispatch.

Events cross as the envelope of
:class:`~domino.events.serialization.EventRegistry`, so both ends register the
types they exchange.
"""

from domino.integrations.kafka.consumer import AsyncKafkaConsumer, Deduplicator
from domino.integrations.kafka.publisher import (
    DEFAULT_TOPIC,
    AsyncKafkaPublisher,
    aggregate_key,
)

__all__ = [
    "DEFAULT_TOPIC",
    "AsyncKafkaPublisher",
    "aggregate_key",
    "AsyncKafkaConsumer",
    "Deduplicator",
]
