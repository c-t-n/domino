# Kafka

Redis Streams and RabbitMQ move events between services. Kafka **keeps** them: a
topic is a durable, replayable log, so a service that did not exist yesterday can
join today and read the history from the beginning. Nothing is deleted when you
consume — the committed offset only records how far *your group* has read.

That, and ordering guarantees per partition, is what makes it worth the extra
operational weight.

```bash
uv add "pydomino[kafka]"
# or: pip install "pydomino[kafka]"
```

!!! note "Async only"
    Built on `aiokafka`, like the [RabbitMQ integration](rabbitmq.md) is on
    aio-pika. A synchronous application drives it through
    [`AsyncOutboxRelay`](sqlalchemy.md#the-transactional-outbox).

## Pick a key

This is the decision that matters. Kafka orders records **within a partition**,
and the key chooses the partition — so keying on the aggregate's id keeps
everything that happened to one order in the order it happened, while different
orders still spread across the cluster:

```python
from domino.integrations.kafka import AsyncKafkaPublisher, aggregate_key

publisher = AsyncKafkaPublisher(
    producer, registry, topic="orders", key=aggregate_key("order_id")
)
```

Without a key, records are spread round-robin and `OrderShipped` can be read
before the `OrderConfirmed` that preceded it. `aggregate_key` reads a field off
the event and falls back to no key when it is absent.

!!! warning "One partition hides the mistake"
    An auto-created topic has a single partition, where everything is ordered no
    matter what you do. Create topics with the partition count you actually
    intend, or the day you scale up will be the day the ordering silently breaks.

## Publishing

```python
from aiokafka import AIOKafkaProducer

producer = AIOKafkaProducer(bootstrap_servers="localhost:9092")
await producer.start()

publisher = AsyncKafkaPublisher(
    producer, registry, topic="orders", key=aggregate_key("order_id")
)
relay = AsyncOutboxRelay(session_factory, outbox, publisher=publisher)
```

As with the other brokers, publishing through the
[outbox](sqlalchemy.md#the-transactional-outbox) is the point.

The publisher uses `send_and_wait`, not fire-and-forget: an outbox relay must not
mark a line as published before the broker has actually taken it.

The record's value is the whole
[envelope](../guide/events.md#leaving-the-process-serialization); the headers
repeat `event_name`, `event_id` and `correlation_id`, so a stream processor or a
console tool can filter without parsing the value.

## Consuming

```python
from aiokafka import AIOKafkaConsumer
from domino.integrations.kafka import AsyncKafkaConsumer

raw = AIOKafkaConsumer(
    "orders",
    bootstrap_servers="localhost:9092",
    group_id="warehouse",
    enable_auto_commit=False,  # Domino commits after dispatching
    auto_offset_reset="earliest",
)
await raw.start()

await AsyncKafkaConsumer(raw, registry, bus=bus).run()
```

Each message reopens the producer's
[correlation scope](../guide/observability.md), so a log line in the consumer
carries the id the original request started with.

!!! danger "Turn auto-commit off"
    Left on, Kafka commits offsets on a timer whether or not your handlers ran.
    A crash then skips events nobody ever handled — and nothing anywhere says so.
    Domino commits *after* dispatching, which is what makes the offset mean
    "handled".

`run_once()` handles one poll's worth of records and commits once for the batch;
`run()` consumes until cancelled, committing after each record. A crash mid-batch
replays that batch, which is the at-least-once behaviour to expect.

### Records that cannot be decoded

Kafka has no queue to leave a bad record in, and refusing to commit would stall
the partition on the same poison record forever. So the consumer forwards it to a
dead-letter topic when you configure one:

```python
AsyncKafkaConsumer(
    raw,
    registry,
    bus=bus,
    dead_letter_producer=producer,
    dead_letter_topic="orders.dead",
)
```

The record is forwarded verbatim — value, key and headers — so it can be replayed
once the missing event type is registered. **Without** a dead-letter topic, the
record is logged and skipped; the log line says so explicitly, because that is a
loss and it should not be silent.

### Duplicates

Delivery is at-least-once end to end. Kafka has nowhere to remember what you
handled, so the consumer takes a `deduplicator` — any `async (event_id) -> bool`
— exactly like the [RabbitMQ one](rabbitmq.md#duplicates). Redis makes a good
ledger.

## A full runnable example

`examples/order_kafka.py` publishes an order's history through an outbox relay,
consumes it in a warehouse service, then has a *reporting* service join with a
new group and replay the whole history — the thing a queue cannot do.

```bash
docker run -d --rm -p 19092:19092 --name redpanda \
  redpandadata/redpanda:latest redpanda start \
  --overprovisioned --smp 1 --memory 512M --node-id 0 --check=false \
  --kafka-addr external://0.0.0.0:19092 \
  --advertise-kafka-addr external://localhost:19092

uv run --extra kafka --extra sqlalchemy python examples/order_kafka.py
```

[Redpanda](https://redpanda.com/) speaks the Kafka protocol, starts in a couple
of seconds and needs no ZooKeeper, which is why Domino's own integration tests
run against it.
