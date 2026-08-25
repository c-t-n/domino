# RabbitMQ

Where a [Redis stream](redis.md) is a log every consumer reads for itself,
RabbitMQ **routes**: a publisher sends to an exchange with a routing key, and the
bindings decide which queues receive it. Adding a service means adding a binding
— the producer never learns it exists.

That, plus per-queue retries and a dead-letter path, is what makes it the fit
when the broker should own the routing.

```bash
uv add "pydomino[rabbitmq]"
# or: pip install "pydomino[rabbitmq]"
```

!!! note "Async only"
    The integration is built on `aio-pika`, an async client; a synchronous
    application drives it through
    [`AsyncOutboxRelay`](sqlalchemy.md#the-transactional-outbox). The sync
    alternative would be a different library altogether, so there is no sync
    twin here — unlike the rest of Domino.

## The topology

Two helpers declare what a Domino producer and consumer expect:

```python
import aio_pika
from domino.integrations.rabbitmq import declare_event_exchange, declare_event_queue

connection = await aio_pika.connect_robust("amqp://…")
channel = await connection.channel()

exchange = await declare_event_exchange(channel)  # durable topic exchange

warehouse = await declare_event_queue(
    channel, "warehouse", exchange=exchange, routing_keys=["OrderConfirmed"]
)
auditor = await declare_event_queue(
    channel,
    "audit",
    exchange=exchange,
    routing_keys=["#"],  # everything
)
```

A **topic** exchange lets a queue bind to one event, to a family
(`Order.*`), or to all of them. Each consuming service owns a durable queue;
several instances of that service consume it together and RabbitMQ shares the
messages between them — competing consumers, with no group to configure.

`declare_event_queue` also declares `<name>.dlx` and `<name>.dead`, and points
the queue at them. That dead-letter path is what makes rejecting a message safe:
it lands somewhere you can look at it. Pass `dead_letter=False` to opt out, or
declare the topology yourself with your own tooling — none of this is required.

## Publishing

```python
from domino.integrations.rabbitmq import AsyncRabbitMQPublisher

publisher = AsyncRabbitMQPublisher(exchange, registry)
relay = AsyncOutboxRelay(session_factory, outbox, publisher=publisher)
```

As with Redis, publishing through the
[outbox](sqlalchemy.md#the-transactional-outbox) is the point: the outbox
guarantees the event survives the commit, RabbitMQ routes it onward.

Messages are **persistent** by default, so a broker restart does not drop what
is still queued. `persistent=False` trades that for throughput, which is rarely
what domain events want.

The routing key defaults to the event's name; `routing_key=` takes a fixed
string or a callable:

```python
AsyncRabbitMQPublisher(
    exchange, registry, routing_key=lambda e: f"orders.{e.event_name}"
)
```

The body is the whole
[envelope](../guide/events.md#leaving-the-process-serialization). The AMQP
properties mirror its identity — `message_id`, `correlation_id`, `type`,
`timestamp` — so a management UI, a tracing tool or a non-Domino consumer can
read them without parsing the body, while the body stays the source of truth.
That redundancy is deliberate: the AMQP timestamp only has second resolution,
and `occurred_on` does not lose its microseconds in the envelope.

## Consuming

```python
from domino.integrations.rabbitmq import AsyncRabbitMQConsumer

bus = AsyncEventBus()
bus.register(OrderConfirmed, ReserveStock())

consumer = AsyncRabbitMQConsumer(warehouse, registry, bus=bus)
await consumer.run()  # until cancelled; run_once() handles what is waiting
```

Each message reopens the producer's
[correlation scope](../guide/observability.md), so a log line in the consumer
carries the id the original request started with.

### Settling a message

A message is acknowledged **after** the bus has dispatched it, so a consumer
killed mid-message leaves it on the queue for another instance.

One that cannot be decoded — an unregistered event type, a malformed body — is
**rejected without requeue**, which sends it to the dead-letter exchange.
Requeueing would spin the same broken message forever; dropping it silently
would be worse. Handler failures are a different matter: the bus logs them and
moves on, then the message is acknowledged, so a handler that must not lose its
work makes that durable itself.

### Duplicates

Delivery is at-least-once end to end. RabbitMQ has no store to remember what you
handled, so the consumer takes a `deduplicator` — any `async (event_id) -> bool`
saying whether the event was already processed. Redis makes a good ledger:

```python
async def already_seen(event_id: str) -> bool:
    return not await redis.set(f"seen:{event_id}", "1", nx=True, ex=86_400)


AsyncRabbitMQConsumer(queue, registry, bus=bus, deduplicator=already_seen)
```

Without one, handlers should be idempotent — worth aiming for regardless.

## A full runnable example

`examples/order_rabbitmq.py` wires both sides and shows the broker doing the
routing: a warehouse bound to `OrderConfirmed` and an auditor bound to
everything, fed by the same publisher.

```bash
docker run -d --rm -p 5672:5672 --name rabbit rabbitmq:3-alpine
uv run --extra rabbitmq --extra sqlalchemy python examples/order_rabbitmq.py
```

It needs a real broker: unlike Redis, RabbitMQ has no faithful in-memory
substitute. For the same reason, Domino's own test suite drives this integration
through doubles, plus a live round-trip that runs when `RABBITMQ_URL` is set.
