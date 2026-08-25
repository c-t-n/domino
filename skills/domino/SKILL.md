---
name: domino
description: >-
  Build or modify Python code that uses the Domino DDD library. USE THIS SKILL —
  don't rely on memory or reverse-engineer the API — whenever `domino` appears in
  a project's imports or dependencies, or whenever you model or wire a Domino
  domain/application layer: value objects, entities, aggregates, domain events,
  an event bus and handlers, repositories, a unit of work, commands, or use
  cases. It also covers Domino's correlation ids, self.log logging, and central
  configure(). Reach for it even for a small change and even when the task looks
  doable unaided: Domino uses a decorator-free class style (subclass a base,
  NEVER add @dataclass) plus event/correlation/logging wiring that are easy to
  get subtly wrong from memory, so the skill encodes the exact conventions and
  can scaffold a new bounded context. Trigger for any "add an aggregate / value
  object / event / repository / use case", "model this domain", or "refactor to
  Domino" request, even if the user doesn't name the library.
---

# Building with Domino

Domino is a small, dependency-free library (Python 3.12+) for **tactical
Domain-Driven Design**. It gives you base classes for the DDD building blocks and
applies the right `@dataclass` for you, so your domain reads as plain classes
with fields. This skill captures how to use it correctly.

Scope note: Domino implements the **domain-events** pattern (an aggregate records
events for you to publish), **not** event sourcing — there is no event store and
aggregates are not rebuilt from a stream. Don't invent one.

## The one rule that surprises people first

**Never put `@dataclass` on a class that subclasses a Domino base.** The base
already applies the correct dataclass in `__init_subclass__` (and declares it to
type checkers via PEP 681 `@dataclass_transform`). You just subclass and declare
fields:

```python
from decimal import Decimal
from domino import ValueObject


class Money(ValueObject):  # NOT @dataclass — the base handles it
    amount: Decimal
    currency: str
```

Adding your own decorator applies dataclass twice and can fight the base's
frozen/eq settings. If you see `@dataclass` above a `ValueObject`, `DomainEvent`,
`Entity`, `AggregateRoot` or `Command` subclass, remove it.

Each base picks the dataclass flavour that fits its meaning:

| Base | Becomes | Why |
| --- | --- | --- |
| `ValueObject` | frozen dataclass | value equality + immutability |
| `DomainEvent` | frozen, `kw_only` dataclass | immutable record; kw-only so subclasses add fields after inherited defaults |
| `Command` | frozen dataclass | immutable request DTO |
| `Entity` / `AggregateRoot` | mutable dataclass, `eq=False` | identity-based equality, mutable lifecycle |

## Building blocks — when to reach for each

- **`ValueObject`** — a concept defined by its attributes, not identity (Money,
  Address, EmailAddress). Immutable; compare by value. Validate in
  `__post_init__`. Use `.replace(**changes)` to get a modified copy.
- **`Entity`** — a thing with a lifecycle and identity (`id`). Two entities are
  equal iff their ids match. Declare an `_id` field.
- **`AggregateRoot`** — an entity that is the consistency boundary and the only
  entry point for changing the cluster inside it. Records domain events with
  `self._add_event(...)`; the app pulls them with `pull_pending_events()` after
  the transaction commits.
- **`DomainEvent`** — an immutable, past-tense record of something that happened
  (`OrderConfirmed`). Carries only what handlers need. `event_id`, `occurred_on`
  and `correlation_id` are inherited and auto-filled — never redeclare them.
- **`EventBus` / `EventHandler`** — in-memory publish/subscribe. A handler reacts
  to consequences (reserve stock, send mail), never the primary action.
- **`AsyncEventBus` / `AsyncEventHandler`** — the same publish/subscribe with an
  awaited `handle`, for handlers doing IO. `AsyncEventPublisher` is the port a
  broker client implements; an `AsyncUnitOfWork` accepts either kind.
- **`Outbox`** (SQLAlchemy) — writes the queued events to a table inside the
  transaction that produced them, so nothing is lost between the commit and the
  publish. An `OutboxRelay` ships them afterwards, at-least-once.
- **Redis Streams** (`domino.integrations.redis`) — a publisher writing events to
  a stream and a consumer group reading them back into a local bus, reopening the
  producer's correlation scope. Pair the publisher with an outbox relay.
- **RabbitMQ** (`domino.integrations.rabbitmq`) — a publisher to a topic exchange
  and a consumer per queue, with a dead-letter path for what cannot be decoded.
  Async only. Reach for it when the broker should own the routing.
- **Kafka** (`domino.integrations.kafka`) — a durable replayable log. Key on the
  aggregate id (`aggregate_key("order_id")`) or ordering is lost. Offsets commit
  after dispatch; auto-commit must stay off. Async only.
- **`EventRegistry`** — encodes an event into a transport envelope
  (`event_name` / `event_id` / `occurred_on` / `correlation_id` / `payload`) and
  rebuilds it on the other side. Only needed when an event leaves the process.
- **`Repository[T]`** — a collection-like port for one aggregate type. Returns
  full aggregates, keyed by identity. Implement it in the infrastructure layer.
  `AsyncRepository[T]` is the same port with `async` operations.
- **`UnitOfWork`** — a thin transaction boundary that also exposes repositories.
  It does **not** track changes; you call `repo.save(...)` yourself. Give it an
  `event_bus` and queue events with `enqueue_events(...)` to have them published
  after commit — the queue is per-scope, dropped on rollback and cleared on exit.
  `AsyncUnitOfWork` is the `async with` twin.
- **`Command`** — the immutable input DTO for a use case.
- **`UseCase[C, R]`** — the application entry point for one user goal. Its base
  `__init__` takes the unit of work (`self._uow`). Thin: validate input, drive the
  domain, manage the transaction, return a result. `AsyncUseCase[C, R]` is the
  async twin, over an `AsyncUnitOfWork`.

## Layering

Keep the dependency arrow pointing inward:

```
application/   use cases, commands   (orchestrates the domain)
domain/        value objects, entities, aggregates, events, domain services
infrastructure repositories, event bus wiring, DB sessions   (implements ports)
```

The domain layer must not import infrastructure. Use cases depend on repository
*interfaces* (`Repository[T]`), not concrete stores.

## Core patterns (copy these shapes)

### Value object with validation

```python
from decimal import Decimal
from domino import ValueObject, DomainValidationError


class Money(ValueObject):
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise DomainValidationError("amount cannot be negative")

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise DomainValidationError("currency mismatch")
        return Money(self.amount + other.amount, self.currency)
```

### Aggregate that records events

Give every field a default (frozen ordering + convenient construction). Declare
`_id` with `default_factory=DomainId.generate`. Add an `updated_at` field if you
call `self._touch()` (without that field `_touch()` is simply a no-op). You do **not** declare a field for pending events — the base
manages them.

```python
from dataclasses import field
from datetime import UTC, datetime
from domino import AggregateRoot, DomainEvent, DomainId, DomainStateError


class OrderConfirmed(DomainEvent):
    order_id: DomainId  # event_id / occurred_on / correlation_id inherited


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    status: str = "draft"
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def confirm(self) -> None:
        if self.status != "draft":
            raise DomainStateError("only draft orders can be confirmed")
        self.status = "confirmed"
        self._touch()
        self._add_event(OrderConfirmed(order_id=self._id))
```

### Repository (port) + an in-memory implementation

```python
from domino import Repository, DomainId


class OrderRepository(Repository[Order]):
    def __init__(self) -> None:
        self._store: dict[DomainId, Order] = {}

    def get_by_id(self, id: DomainId) -> Order | None:
        return self._store.get(id)

    def save(self, aggregate: Order) -> None:
        self._store[aggregate.id] = aggregate

    def delete(self, id: DomainId) -> None:
        self._store.pop(id, None)
```

### Command + use case (with the transaction boundary)

```python
from domino import Command, DomainId, UnitOfWork, UseCase, EventBus


class PlaceOrderCommand(Command):
    customer_id: DomainId


class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    # the base __init__ takes the unit of work and stores it as self._uow

    def execute(self, command: PlaceOrderCommand) -> DomainId:
        orders = self._uow.repository("orders")  # or self._uow.orders
        order = Order()
        order.confirm()
        orders.save(order)
        self._uow.enqueue_events(*order.pull_pending_events())  # sent AFTER commit
        return order.id


uow = UnitOfWork({"orders": repo}, event_bus=bus)

with uow:  # commit on clean exit, rollback on error
    order_id = PlaceOrder(uow).execute(PlaceOrderCommand(customer_id=cid))
```

The scope can also be opened inside `execute` (`with self._uow:`) when the use
case owns the transaction — pick one and stay consistent.

Wire a real database through the UoW hooks:
`UnitOfWork({"orders": repo}, commit=session.commit, rollback=session.rollback)`.
With an in-memory store that writes on `save`, the hooks default to no-ops.

### Event bus wiring

```python
bus = EventBus()
bus.register(OrderConfirmed, InventoryHandler())
bus.register(OrderConfirmed, EmailHandler())  # many handlers per event is fine
# or: bus.register_all([(OrderConfirmed, InventoryHandler()), ...])
```

Handlers are wrapped so a failing one is logged, not propagated. A handler
usually guards on `isinstance(event, OrderConfirmed)` and reacts only to its type.

## Cross-cutting features (they need zero plumbing)

### Correlation ids — automatic

Every `UseCase.execute` runs inside an ambient correlation scope (a
`contextvars` context). Every `DomainEvent` created during it captures that id as
`event.correlation_id`. You never pass it around. A nested use case reuses the
caller's id; if the command carries a `correlation_id`, that trace is continued.
At other boundaries (web middleware, a message consumer) open the scope yourself:

```python
from domino import correlation_scope

with correlation_scope(incoming_id):  # or no arg to generate one
    handle(message)
```

### Contextual logging — `self.log`

Use cases, event handlers and aggregate roots have `self.log`. It stamps every
line with the class name and the current correlation id automatically:

```python
def execute(self, command: PlaceOrderCommand) -> DomainId:
    self.log.info("placing order for %s", command.customer_id)
    ...


# INFO domino [PlaceOrder] [cid=8f3e…] placing order for 7ff8…
```

Domino logs to the `domino` logger and never configures logging — the app does
(`logging.basicConfig(level="INFO")`). Mix `LoggerMixin` into your own classes
(a domain service, a repository) to get the same `self.log`.

### Central configuration — `configure()` once at startup

Tune cross-cutting behaviour in one call; only what you pass changes.

```python
from uuid import uuid4
from domino import configure

configure(correlation_id_factory=lambda: uuid4().hex[:16])  # 16-char cids
# NanoID for ids too:  configure(id_factory=generate, correlation_id_factory=lambda: generate(size=16))
```

## Pitfalls to avoid

- Adding `@dataclass` yourself (see the top rule).
- Redeclaring `event_id` / `occurred_on` / `correlation_id` on an event — they're
  inherited.
- Forgetting the `_id` field on an entity/aggregate, or giving a non-default field
  after a defaulted one (dataclass ordering error).
- Mutating a value object or event — they're frozen; build a new one (`.replace`).
- Publishing events before the transaction commits, or calling
  `pull_pending_events()` twice (it clears the list).
- Putting business logic in a use case — it belongs in the aggregate or a domain
  service. The use case only orchestrates.
- Making `UnitOfWork` do change tracking — it doesn't; save through the repo.
- Expecting event sourcing — Domino records events to publish, nothing more.

## Bundled resources

- **`references/cheatsheet.md`** — a compact API reference (every base, its
  construction style, and key method signatures). Read it when you need an exact
  signature or a quick reminder.
- **`references/order_domain.py`** — a complete, runnable example wiring every
  building block together (value objects, aggregate, events, handlers, bus,
  repository, UoW, commands, two use cases, correlation + logging). Read or adapt
  it when building something end-to-end.
- **`scripts/scaffold.py`** — generate a bounded-context skeleton (domain /
  application / infrastructure folders with correct starter stubs). Run:
  `python scripts/scaffold.py <context_name> [--path DIR]`. Prefer this over
  hand-creating the folder tree for a new context.

## Verifying your work

If the project has the dev toolchain, run the checks after writing code:

```bash
uv run ruff check     # lint (Domino enforces no stray @dataclass via review, not lint)
uv run ty check       # type-check — confirms your classes typecheck as dataclasses
uv run pytest         # tests
```

`ty` is the fastest way to catch a mis-wired class: if a constructor call or field
access is wrong, it will flag it, because the dataclass_transform makes the
generated `__init__` visible to the checker.
