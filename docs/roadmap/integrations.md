# Integration roadmap

Domino ships two integrations today — [SQLAlchemy](../infrastructure/sqlalchemy.md)
and [FastAPI](../presentation/fastapi.md). This page lists what else could plug
into the existing ports, what stands in the way, and in which order it is worth
building.

!!! warning "Most of this is not implemented yet"
    These are candidates, not commitments, and the sketches below show *proposed*
    These are candidates, not commitments, and the sketches below show
    *proposed* APIs — except where a section says otherwise. Shipped: the three
    prerequisites, and Redis Streams, RabbitMQ and Kafka (publisher **and**
    consumer for each). The cloud queues and the stores below are still
    unbuilt.

## The ports an integration plugs into

Every integration implements one of the interfaces the domain already depends on,
so the domain layer never learns that Redis or Kafka exist:

| Port | Contract | Implemented today by |
|------|----------|----------------------|
| `Repository[T]` / `AsyncRepository[T]` | `get_by_id` / `save` / `delete` on whole aggregates | `SqlAlchemyRepository`, `AsyncSqlAlchemyRepository` |
| `UnitOfWork` / `AsyncUnitOfWork` | one transactional scope, publishes queued events on commit | `SqlAlchemyUnitOfWork`, `AsyncSqlAlchemyUnitOfWork` |
| `EventPublisher` | `publish(*events) -> None` | `EventBus` (in-process) |
| `EventHandler` | `handle(event) -> None` | your handlers, wrapped in `SafeEventHandler` |
| `Specification` | composable criteria, evaluated in memory **or** translated to a query | `Filterable` / `AsyncFilterable` (SQL) |

`EventPublisher` is the shortest path to a broker: the unit of work already calls
it after a successful commit, so a Redis or RabbitMQ publisher drops in with no
change to a use case.

## Three prerequisites

These are transverse — every broker integration needs them, so they come first.

### 1. Event serialization — done

`EventRegistry` encodes an event into a transport envelope and rebuilds it on the
other side; see
[Domain events](../guide/events.md#leaving-the-process-serialization) for the
full contract.

```python
registry = EventRegistry()
registry.register(OrderConfirmed)

envelope = registry.encode(event)  # a plain dict — or encode_json(event)
same = registry.decode(envelope)
```

`event_name`, `event_id`, `occurred_on` and `correlation_id` sit at the top level
of the envelope, so a consumer can deduplicate and continue the trace without
decoding the payload first.

### 2. An async publisher port — done

`AsyncEventPublisher` is the awaited counterpart of `EventPublisher`, and
`AsyncUnitOfWork` awaits it on commit:

```python
class KafkaPublisher(AsyncEventPublisher):
    async def publish(self, *events: DomainEvent) -> None: ...
```

The unit of work dispatches on the returned value rather than on the bus type,
so a synchronous `EventBus` still works under an async unit of work.
`AsyncEventBus` and `AsyncEventHandler` are the in-memory implementations — see
[Domain events](../guide/events.md#on-an-async-stack).

### 3. Atomicity between the commit and the publish — done

The [transactional outbox](../infrastructure/sqlalchemy.md#the-transactional-outbox)
writes events to a table inside the transaction that produced them, and a relay
publishes them afterwards:

```python
outbox = Outbox(registry, metadata=metadata)
uow = AsyncSqlAlchemyUnitOfWork(session_factory, repos, outbox=outbox)

async with uow:  # one transaction
    await uow.orders.save(order)
    uow.enqueue_events(*order.pull_pending_events())

relay = AsyncOutboxRelay(session_factory, outbox, publisher=broker)
await relay.run_once()
```

Delivery is at-least-once, which is the honest guarantee across two systems —
consumers deduplicate on `event_id`.

## Candidate integrations

### Messaging (`EventPublisher`)

| Infrastructure | What it brings | Notes |
|---|---|---|
| ~~**Outbox (SQLAlchemy)**~~ | at-least-once delivery, broker-agnostic | Shipped — see prerequisite 3 |
| ~~**Redis Streams**~~ | consumer groups, replay, a light dependency | Shipped — see the [guide](../infrastructure/redis.md) |
| ~~**RabbitMQ**~~ (aio-pika) | topic routing, dead-letter queues, retries | Shipped — see the [guide](../infrastructure/rabbitmq.md) |
| ~~**Kafka**~~ (aiokafka) | durable log, replay, partitioning by aggregate id | Shipped — see the [guide](../infrastructure/kafka.md) |
| **Cloud queues** (SQS/SNS, Pub/Sub) | managed infrastructure | Same port, different client |

Redis pub/sub is deliberately absent: it drops messages when no subscriber is
listening, which makes it unfit for domain events.

### Consuming events (`EventHandler`) — done for all three brokers

Each integration reads into a local event bus and reopens the producer's
[correlation scope](../guide/observability.md), so a trace spans services. They
differ where the broker does: Redis deduplicates through a `dedupe_ttl` (it is
its own ledger), RabbitMQ and Kafka take a `deduplicator` callable since neither
has anywhere to remember. What they cannot decode goes to a dead-letter queue
(RabbitMQ), a dead-letter topic (Kafka), or stays pending (Redis).

### Persistence (`AsyncRepository`, `AsyncUnitOfWork`)

| Infrastructure | Notes |
|---|---|
| **MongoDB** (motor) | One aggregate ↔ one document maps cleanly onto "a repository returns a whole aggregate". Needs a `Specification` → query translator, mirroring the SQL one |
| **Redis** | Read-through cache in front of a repository, and **distributed locks** to protect an aggregate's invariant under concurrency |
| **DynamoDB**, **Postgres via asyncpg** | The `commit` / `rollback` hooks already exist; wiring another store is mechanical |

### Observability

**OpenTelemetry** is the highest-value-per-line item on this page. Correlation ids
already flow through `contextvars` and land on every event and log record; mapping
them onto a trace id, and opening a span per use case, needs very little code.

### Presentation

The `install_domino` pattern generalises: **Typer** for a CLI, **ARQ** or
**Celery** for background jobs, **gRPC** for service APIs. Same use cases, another
door in.

## Suggested order

1. ~~**Event serialization + registry**~~ — shipped, see above.
2. ~~**`AsyncEventPublisher`** and the async unit of work awaiting it~~ — shipped.
3. ~~**Transactional outbox**~~ — shipped, and independent of any broker.
4. ~~**Redis Streams**~~ — shipped, publisher and consumer.
5. ~~**A consumer runtime**~~ — shipped with it: correlation and deduplication.
6. ~~**RabbitMQ**~~ — shipped, with topic routing and a dead-letter path.
7. ~~**Kafka**~~ — shipped, keyed on the aggregate id so history stays ordered.

All seven are done: an event can leave a transaction reliably, reach a stream, an
exchange or a log, and be handled by another service under the same trace. What
remains — the cloud queues, and the stores further down — is a different
exercise, closer to the SQLAlchemy integration than to these.

## What will not change

An integration lives in `domino.integrations.<name>`, behind an optional extra,
and implements a port the domain already depends on. The domain and application
layers keep importing interfaces only — a rule the
[layering guide](../ddd/layering.md) spells out, and the reason any of this can be
swapped at all.
