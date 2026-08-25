# Redis Streams

A Redis stream is an append-only log with **consumer groups**: several services
read the same events at their own pace, a crashed consumer picks up where it
stopped, and unacknowledged entries stay visible. That makes it the lightest
broker that still gives real delivery guarantees — and the natural first step out
of a single process.

```bash
uv add "pydomino[redis]"
# or: pip install "pydomino[redis]"
```

The integration is two halves: a publisher writing to a stream, and a consumer
reading it back into a local [event bus](../guide/events.md).

## Both ends share a registry

Events cross the wire as the
[envelope](../guide/events.md#leaving-the-process-serialization) of an
`EventRegistry`, so **both services register the types they exchange**:

```python
registry = EventRegistry()
registry.register(OrderConfirmed)
```

A consumer that meets an event it never registered does not guess — see
[below](#events-nobody-registered).

## Publishing

```python
from redis.asyncio import Redis
from domino.integrations.redis import AsyncRedisStreamPublisher

publisher = AsyncRedisStreamPublisher(Redis(), registry, maxlen=10_000)
await publisher.publish(*order.pull_pending_events())
```

`RedisStreamPublisher` is the sync twin. Both are ordinary
[`EventPublisher`](../guide/events.md#on-an-async-stack) implementations, so they
drop into a unit of work — or, better, into an
[outbox relay](sqlalchemy.md#the-transactional-outbox):

```python
relay = AsyncOutboxRelay(session_factory, outbox, publisher=publisher)
```

That pairing is the point: the outbox guarantees the event survives the commit,
the stream carries it to whoever is listening.

**Routing.** `stream=` takes a name or a callable, so events can be split per
type or per bounded context:

```python
AsyncRedisStreamPublisher(client, registry, stream=lambda e: f"domino:{e.event_name}")
```

**Trimming.** `maxlen=` caps the stream, because a log nobody trims grows until
Redis runs out of memory. Trimming is approximate by default, which is what you
want in production — exact trimming costs more for no practical gain.

An entry keeps the envelope's fields flat (`event_name`, `event_id`,
`occurred_on`, `correlation_id`, `payload`), so `XRANGE` stays readable while
you debug and a consumer can route on the name without decoding the payload.

## Consuming

```python
from domino import AsyncEventBus
from domino.integrations.redis import AsyncRedisStreamConsumer

bus = AsyncEventBus()
bus.register(OrderConfirmed, ReserveStock())

consumer = AsyncRedisStreamConsumer(
    Redis(), registry, bus=bus, group="warehouse", consumer="worker-1"
)
await consumer.ensure_group()
await consumer.run()  # until cancelled; run_once() for one batch
```

`ensure_group` creates the group and the stream if they are missing, and does
nothing if they exist, so a worker is safe to restart.

Every instance of a service shares one `group` with a distinct `consumer` name:
Redis then splits the entries between them, and each entry is delivered to one
member of the group.

### The correlation id crosses with the event

Each message reopens the producer's
[correlation scope](../guide/observability.md), so a log line in the consumer
carries the id the original request started with:

```
INFO domino [PlaceOrder]    [cid=8f3e…] placing order       ← the API service
INFO domino [ReserveStock]  [cid=8f3e…] reserving stock     ← the worker
```

That is the whole reason the id sits at the top of the envelope rather than
inside the payload.

### Acknowledgement

An entry is acknowledged **after** the bus has dispatched it. A worker killed
mid-message leaves the entry unacknowledged, so it stays in the group's pending
list and another consumer can claim it.

Handler failures do not block anything: the bus wraps every handler, logs what
broke and moves on, then the entry is acknowledged. A handler that must not lose
its work should make that durable itself — write to a table, enqueue a retry —
rather than rely on the stream to replay it.

### Duplicates

Delivery is at-least-once, end to end: the outbox may resend after a crash, and
so may Redis. Pass `dedupe_ttl` and the consumer skips an `event_id` it has
already processed, using Redis itself as the ledger:

```python
AsyncRedisStreamConsumer(..., dedupe_ttl=timedelta(hours=24))
```

Pick a window longer than any plausible redelivery. Without it, a handler must
be idempotent on its own — which is worth aiming for regardless.

### Events nobody registered {: #events-nobody-registered }

An entry the consumer cannot decode — an event type it never registered, a
malformed payload — is logged and **left unacknowledged**, not dropped. It shows
up in `XPENDING`, where you can see it, register the missing type and let a
worker claim it, or acknowledge it deliberately. Silence would be worse: an
event would vanish with nothing to show for it.

## A full runnable example

`examples/order_redis.py` publishes through an outbox relay and consumes the
same events back, correlation id included, against an in-memory Redis:

```bash
uv run --extra redis --extra sqlalchemy python examples/order_redis.py
```

It runs against `fakeredis`, so no server is needed; pointing the client at a
real `redis.asyncio.Redis` changes nothing else.
