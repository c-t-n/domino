# Integration roadmap

Domino ships two integrations today — [SQLAlchemy](../infrastructure/sqlalchemy.md)
and [FastAPI](../presentation/fastapi.md). This page lists what else could plug
into the existing ports, what stands in the way, and in which order it is worth
building.

!!! warning "Nothing here is implemented yet"
    These are candidates, not commitments, and the sketches below show *proposed*
    APIs. Only `domino.integrations.sqlalchemy` and `domino.integrations.fastapi`
    exist today.

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

### 1. Event serialization

`DomainEvent` is a frozen dataclass with no `to_dict` / `from_dict`, and nothing
maps an event *name* back to its class. Crossing a process boundary needs a stable
envelope and a registry to rebuild the event on the other side:

```python
{
  "event_name": "OrderConfirmed",
  "event_id": "…",
  "occurred_on": "2026-08-25T10:11:12Z",
  "correlation_id": "…",
  "payload": {"order_id": "…", "total": "42.00"}
}
```

`event_name`, `event_id`, `occurred_on` and `correlation_id` already exist on the
base class — only the payload codec and the name → class registry are missing.
This unlocks everything else on this page.

### 2. An async publisher port

`EventPublisher.publish` is synchronous, and `AsyncUnitOfWork.commit()` calls it
without awaiting. Every modern client (aiokafka, aio-pika, `redis.asyncio`) is
async, so the port needs an async sibling and the async unit of work needs to
await it:

```python
class AsyncEventPublisher(ABC):
    @abstractmethod
    async def publish(self, *events: DomainEvent) -> None: ...
```

### 3. Atomicity between the commit and the publish

Events are published *after* the transaction commits. If the process dies in
between, they are lost — silently, and no broker fixes that. The remedy is the
**transactional outbox**: write the events inside the same transaction, and let a
relay publish them afterwards.

```python
with uow:                                  # one transaction
    orders.save(order)
    uow.enqueue_events(*order.pull_pending_events())
    # the outbox publisher writes them to an `outbox` table here,
    # so rows and events commit together — a relay ships them later
```

The explicit `enqueue_events` queue is already the right shape for this: the unit
of work knows exactly which events belong to the scope.

## Candidate integrations

### Messaging (`EventPublisher`)

| Infrastructure | What it brings | Notes |
|---|---|---|
| **Outbox (SQLAlchemy)** | at-least-once delivery, broker-agnostic | Fixes prerequisite 3; useful even with no broker at all |
| **Redis Streams** | consumer groups, replay, a light dependency | The cheapest way to validate the publisher/consumer contract |
| **RabbitMQ** (aio-pika) | topic routing, dead-letter queues, retries | The natural fit for service-to-service integration |
| **Kafka** (aiokafka) | durable log, replay, partitioning by aggregate id | The only one that also opens the door to event sourcing |
| **Cloud queues** (SQS/SNS, Pub/Sub) | managed infrastructure | Same port, different client |

Redis pub/sub is deliberately absent: it drops messages when no subscriber is
listening, which makes it unfit for domain events.

### Consuming events (`EventHandler`)

Domino publishes today but never consumes. A worker integration is the missing
half: subscribe to a stream, deserialize the envelope, open a
[correlation scope](../guide/observability.md) from its `correlation_id` — so a
trace spans services — and route to the registered handlers. Consumers must also
deduplicate on `event_id`, since delivery is at-least-once.

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

1. **Event serialization + registry** — nothing else plugs in without it.
2. **`AsyncEventPublisher`** and the async unit of work awaiting it.
3. **Transactional outbox** — delivery guarantees, independent of any broker.
4. **Redis Streams** — first real broker, cheap to run in a test container.
5. **A consumer runtime** — closes the loop, with correlation and deduplication.
6. **RabbitMQ or Kafka**, whichever matches the deployment.

Steps 1 to 3 are worth doing on their own merits: they make publishing reliable
whatever the eventual target.

## What will not change

An integration lives in `domino.integrations.<name>`, behind an optional extra,
and implements a port the domain already depends on. The domain and application
layers keep importing interfaces only — a rule the
[layering guide](../ddd/layering.md) spells out, and the reason any of this can be
swapped at all.
