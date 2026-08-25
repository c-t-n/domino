# SQLAlchemy

Domino's core has no dependencies. The optional `domino.integrations.sqlalchemy` subpackage
implements the infrastructure layer — repositories and a unit of work — against
[SQLAlchemy](https://www.sqlalchemy.org/) 2.0.

```bash
uv add "pydomino[sqlalchemy]"
# or: pip install "pydomino[sqlalchemy]"
```

## Persistence-ignorant by design

The integration uses SQLAlchemy's **imperative mapping**: your domain classes stay
exactly as they are — plain Domino aggregates, entities and value objects with
**zero SQLAlchemy imports** — and you map them to tables separately. The payoff is
that the mapped class *is* your aggregate, so a repository returns real `Order`
objects, not separate "ORM models" you translate back and forth.

!!! note "Why not declarative mapping?"
    Making an aggregate inherit `DeclarativeBase` fails outright — a metaclass
    conflict between SQLAlchemy and Domino's `@dataclass_transform` bases — and
    even the workaround (a parallel "row" model plus hand-written translation)
    means maintaining two models and translating on every load and save.
    Imperative mapping keeps one model: your domain.

## Mapping an aggregate

Define tables, then map the domain classes to them. Value objects map across
columns with `composite()`; aggregate-internal entities map with `relationship()`.

```python
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Numeric, String, Table
from sqlalchemy.orm import composite, registry, relationship

from domino.integrations.sqlalchemy import DomainIdType

metadata = MetaData()
mapper_registry = registry()

orders_table = Table(
    "orders",
    metadata,
    Column("id", DomainIdType, primary_key=True),
    Column("customer_id", DomainIdType, nullable=False),
    Column("status", String(20), nullable=False),
)
order_lines_table = Table(
    "order_lines",
    metadata,
    Column("id", DomainIdType, primary_key=True),
    Column("order_id", DomainIdType, ForeignKey("orders.id"), nullable=False),
    Column("product", String(100), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("unit_price_amount", Numeric(12, 2), nullable=False),
    Column("unit_price_currency", String(3), nullable=False),
)

mapper_registry.map_imperatively(
    OrderLine,
    order_lines_table,
    properties={
        "_id": order_lines_table.c.id,
        "unit_price": composite(  # value object across two columns
            Money,
            order_lines_table.c.unit_price_amount,
            order_lines_table.c.unit_price_currency,
        ),
    },
)
mapper_registry.map_imperatively(
    Order,
    orders_table,
    properties={
        "_id": orders_table.c.id,
        "lines": relationship(OrderLine, cascade="all, delete-orphan"),  # children
    },
)
```

Two details worth noting:

- The primary-key attribute is Domino's `_id`, so map it explicitly:
  `"_id": table.c.id`. The rest of the columns map to same-named attributes
  automatically.
- Domino value objects are frozen dataclasses, which `composite()` supports
  natively — no extra glue.

### `DomainIdType`

A `TypeDecorator` that stores a `DomainId` as text and rebuilds it on load.
UUID-backed ids round-trip as UUIDs, string-backed ids as strings. Pass a length
for long string ids: `Column("id", DomainIdType(64))`.

## Repository

Subclass `SqlAlchemyRepository[T]` per aggregate. The aggregate type comes from
the generic parameter — nothing else to declare — and `get_by_id` / `save` /
`delete` are implemented for you. Add domain-specific finders using the session
exposed as `self._session`:

```python
from sqlalchemy import select
from domino.integrations.sqlalchemy import SqlAlchemyRepository


class OrderRepository(SqlAlchemyRepository[Order]):
    def by_customer(self, customer_id: DomainId) -> list[Order]:
        query = select(Order).where(orders_table.c.customer_id == customer_id)
        return list(self._session.scalars(query))
```

!!! tip "Reference the Table column in queries"
    In finders, filter on the **Table** column (`orders_table.c.customer_id`)
    rather than the ORM attribute (`Order.customer_id`). Imperative mapping doesn't
    surface typed columns on the class, so the Table reference is both correct and
    type-checker-friendly.

### Filtering with specifications

Instead of hand-writing a finder per query, mix in `Filterable[T]` to get
`list(*specifications)`. A [specification](../guide/specifications.md) is a
composable, persistence-ignorant criterion built from the field helpers (`eq`,
`ne`, `lt`, `le`, `gt`, `ge`, `in_`, `like`) and combined with `&` / `|` / `~`.

```python
from domino import eq, gt, in_
from domino.integrations.sqlalchemy import Filterable, SqlAlchemyRepository


class OrderRepository(SqlAlchemyRepository[Order], Filterable[Order]): ...


repo.list(eq("status", "confirmed"), in_("customer_id", [c1, c2]))  # AND-ed
repo.list(gt("priority", 5) | eq("status", "urgent"))  # OR
repo.list(~eq("status", "cancelled"))  # NOT
repo.list()  # everything
```

`Filterable` translates the specification into a SQL `WHERE` clause, filtering on
the aggregate's mapped fields. The same specification also evaluates **in memory**
(`spec.is_satisfied_by(order)`), so one criterion can drive both a query and a
domain check — see [Specifications](../guide/specifications.md).

## Unit of work

`SqlAlchemyUnitOfWork` opens **one session per scope**. Give it a session factory
and a mapping of name to repository *class*; entering the `with` block builds the
repositories on a fresh session and drives commit/rollback, and leaving it closes
the session.

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from domino.integrations.sqlalchemy import SqlAlchemyUnitOfWork

engine = create_engine("postgresql+psycopg://…")
session_factory = sessionmaker(engine, expire_on_commit=False)

uow = SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository})

with uow:
    order = uow.orders.get_by_id(order_id)
    order.confirm()
    uow.orders.save(order)
    # commit on clean exit, rollback on exception, session always closed
```

`SqlAlchemyUnitOfWork` *is* a `UnitOfWork` (and `SqlAlchemyRepository` a
`Repository[T]`), so a [use case](../guide/use-cases.md) doesn't change — only how
you construct the unit of work does.

!!! warning "Use `expire_on_commit=False`"
    By default SQLAlchemy expires an instance's attributes on commit, so touching
    an aggregate *after* its unit of work closes raises `DetachedInstanceError`.
    Building the session factory with `expire_on_commit=False` keeps aggregates
    usable after the transaction — the right default for this pattern.

`save` is `session.add`, which is correct for a new or a modified aggregate as
long as it was loaded within the same session (the unit-of-work norm). For a
detached aggregate from a previous session, use `uow.session.merge(aggregate)`.

## Async

Each piece has an `Async*` twin built on SQLAlchemy's `AsyncSession`:
`AsyncSqlAlchemyRepository` (an `AsyncRepository[T]`), `AsyncSqlAlchemyUnitOfWork`
(an `AsyncUnitOfWork`) and `AsyncFilterable`. The API is the same shape — only the
calls are awaited and the unit of work is driven with `async with`. The **domain and the imperative mapping don't change
at all**; only the infrastructure wiring does.

Install the `asyncio` extra (the `sqlalchemy` extra already pulls it in) and add
an async driver — `aiosqlite`, `asyncpg`, `asyncmy`, …:

```bash
uv add "pydomino[sqlalchemy]" aiosqlite
```

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from domino import eq
from domino.integrations.sqlalchemy import (
    AsyncFilterable,
    AsyncSqlAlchemyRepository,
    AsyncSqlAlchemyUnitOfWork,
)


class OrderRepository(AsyncSqlAlchemyRepository[Order], AsyncFilterable[Order]):
    async def by_customer(self, customer_id: DomainId) -> list[Order]:
        result = await self._session.scalars(
            select(Order).where(orders_table.c.customer_id == customer_id)
        )
        return list(result)


engine = create_async_engine("postgresql+asyncpg://…")
session_factory = async_sessionmaker(engine, expire_on_commit=False)
uow = AsyncSqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository})

async with uow:
    order = await uow.orders.get_by_id(order_id)
    order.confirm()
    await uow.orders.save(order)
    confirmed = await uow.orders.list(eq("status", "confirmed"))
    # commit on clean exit, rollback on exception, session always closed
```

!!! note "The whole aggregate is loaded eagerly"
    Async SQLAlchemy can't lazy-load a relationship on attribute access — there's
    no greenlet to bridge the implicit IO, so `order.lines` would raise. The async
    repository therefore eager-loads the aggregate's entire object graph (via
    `selectinload`, recursively) on `get_by_id` and `list`. That's also the DDD
    stance: a repository returns a whole aggregate, not a lazily-stitched shell.

Everything else carries over unchanged: `DomainIdType`, the imperative mapping,
`composite()` for value objects, `relationship()` for child entities, and the
`expire_on_commit=False` recommendation.

!!! tip "Publishing domain events after commit"
    Pass an `event_bus` and the async unit of work dispatches domain events **after
    a successful commit** — the classic "unit of work publishes events" pattern:

    ```python
    uow = AsyncSqlAlchemyUnitOfWork(
        session_factory, {"orders": OrderRepository}, event_bus=bus
    )

    async with uow:
        order.confirm()
        await uow.orders.save(order)
        uow.enqueue_events(*order.pull_pending_events())  # published on commit
    ```

    You choose what leaves the transaction by queueing it with `enqueue_events`;
    the bus is called once the transaction is durable, so your use case never
    touches it itself. The queue is per-scope — a rollback drops it, and exiting
    clears it — so reusing the unit of work never replays an earlier scope. The
    [FastAPI integration](../presentation/fastapi.md) wires this up for you.

## The transactional outbox

Publishing after a commit leaves a window: if the process dies between the two,
the event is gone and nothing records that it existed. The outbox closes it by
writing events to a table **inside the same transaction**, so rows and events
become durable together or not at all.

Declare the table on the metadata your migration already creates, then hand the
outbox to the unit of work:

```python
from domino import EventRegistry
from domino.integrations.sqlalchemy import Outbox, AsyncSqlAlchemyUnitOfWork

registry = EventRegistry()
registry.register(OrderConfirmed)

outbox = Outbox(registry, metadata=metadata)  # declares `domino_outbox`

uow = AsyncSqlAlchemyUnitOfWork(
    session_factory, {"orders": OrderRepository}, outbox=outbox
)

async with uow:
    await uow.orders.save(order)
    uow.enqueue_events(*order.pull_pending_events())
    # the order rows and the outbox lines commit together
```

Nothing reaches the broker yet — that is a relay's job, in a worker process or a
background task:

```python
from domino.integrations.sqlalchemy import AsyncOutboxRelay

relay = AsyncOutboxRelay(session_factory, outbox, publisher=broker)
await relay.run_once()  # publishes one batch, marks the lines sent
await relay.run(poll_interval=1.0)  # or drain it until cancelled
```

`OutboxRelay` is the sync twin. `Outbox` itself holds no connection: it builds
statements, which is why one instance serves both stacks.

!!! warning "At-least-once, so consumers must deduplicate"
    A relay that publishes and then dies before marking the line will send it
    again. That is the honest guarantee of this pattern — exactly-once does not
    exist across two systems. Consumers deduplicate on `event_id`, which the
    [envelope](../guide/events.md#leaving-the-process-serialization) carries.

### What the relay guarantees

Lines go out in the order they were written, and a failure **stops the batch**
rather than skipping ahead: the failing line keeps its place, its `attempts`
counter grows and `last_error` records why, so the next pass resumes exactly
where the broker gave up. Nothing is dropped, and nothing overtakes.

Running several relays against one table is safe on PostgreSQL, MySQL and Oracle,
where the query adds `FOR UPDATE SKIP LOCKED`; the dialect is detected, and
`skip_locked=` overrides it. On SQLite, run a single relay.

### Housekeeping

Published lines stay in the table as an audit trail — you can see what was sent,
when, and how many attempts it took. They also accumulate, so drop the old ones
on a schedule:

```python
from datetime import timedelta

relay.purge(older_than=timedelta(days=7))  # returns how many were removed
```

Only *published* lines are ever deleted: a line still waiting to be sent
survives, however old it is, so a long broker outage cannot cost you an event.
There is deliberately no default retention — deleting is irreversible, so the
window is yours to state.

### Alongside in-process handlers

`event_bus` and `outbox` are independent and combine: the bus dispatches to local
handlers after commit, the outbox carries the same events to the broker. Wanting
both is the normal case — an email sent in-process, an integration event
published outside.

```python
uow = SqlAlchemyUnitOfWork(session_factory, repositories, event_bus=bus, outbox=outbox)
```

## A full runnable example

See `examples/order_sqlalchemy.py` (sync) and `examples/order_sqlalchemy_async.py`
(async) in the repository — the same order domain, mapped and persisted to SQLite
end to end.
