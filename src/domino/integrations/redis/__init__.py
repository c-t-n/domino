"""Redis Streams integration: publish domain events, and consume them.

Optional — install with ``pip install pydomino[redis]``. Domino's core has no
runtime dependencies; importing this subpackage requires ``redis``.

- :class:`RedisStreamPublisher` / :class:`AsyncRedisStreamPublisher` — an
  :class:`~domino.events.publisher.EventPublisher` writing to a stream, ready to
  hand to a unit of work or to an outbox relay;
- :class:`RedisStreamConsumer` / :class:`AsyncRedisStreamConsumer` — the other
  half: a consumer group reading the stream into a local event bus, reopening
  the producer's correlation scope for each message;
- :func:`to_fields` / :func:`to_envelope` — the wire format itself, for reading a
  stream outside a consumer (replaying with ``XRANGE``, an admin tool).

Events cross as the envelope of
:class:`~domino.events.serialization.EventRegistry`, so both ends must register
the types they exchange.
"""

from domino.integrations.redis.consumer import (
    AsyncRedisStreamConsumer,
    RedisStreamConsumer,
)
from domino.integrations.redis.message import to_envelope, to_fields
from domino.integrations.redis.publisher import (
    DEFAULT_STREAM,
    AsyncRedisStreamPublisher,
    RedisStreamPublisher,
)

__all__ = [
    "DEFAULT_STREAM",
    "RedisStreamPublisher",
    "AsyncRedisStreamPublisher",
    "RedisStreamConsumer",
    "AsyncRedisStreamConsumer",
    "to_fields",
    "to_envelope",
]
