# domino

[![PyPI](https://img.shields.io/pypi/v/pydomino.svg)](https://pypi.org/project/pydomino/)
[![CI](https://github.com/c-t-n/domino/actions/workflows/ci.yml/badge.svg)](https://github.com/c-t-n/domino/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/pydomino.svg)](https://pypi.org/project/pydomino/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Types: ty](https://img.shields.io/badge/types-ty-261230.svg)](https://github.com/astral-sh/ty)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A small, dependency-free library for building **Domain-Driven Design** domains
in Python. It gives you clean base classes for the tactical DDD patterns and
gets out of your way — value equality, immutability and event plumbing come
from the standard library (`dataclasses`), which the base classes apply for you.

Just subclass a base and declare your fields: `ValueObject`, `DomainEvent`,
`Entity`, `AggregateRoot` and `Command` turn each subclass into the right kind
of dataclass automatically (frozen, frozen keyword-only, or mutable
identity-based). No `@dataclass` decorator to repeat, and full static typing is
preserved via [PEP 681](https://peps.python.org/pep-0681/) `@dataclass_transform`,
so type checkers still see the generated `__init__`.

Requires Python 3.12+.

## Install

```bash
uv add pydomino
# or, from a checkout:
uv pip install -e .
```

The distribution is `pydomino` (`domino` was taken on PyPI); the import stays
`domino`:

```python
from domino import AggregateRoot, UnitOfWork
```

## The building blocks

| Concept | Class | Purpose |
| --- | --- | --- |
| Value object | `ValueObject` | Immutable, compared by value |
| Entity | `Entity` | Compared by identity (`id`) |
| Aggregate root | `AggregateRoot` | Consistency boundary + records domain events |
| Identity | `DomainId` | UUID- or string-based identifier |
| Domain event | `DomainEvent` | Immutable record of something that happened |
| Event bus | `EventBus` / `EventHandler` | In-memory publish/subscribe |
| Repository | `Repository[T]` / `AsyncRepository[T]` | Collection-like persistence port |
| Unit of work | `UnitOfWork` / `AsyncUnitOfWork` | Transactional boundary around repositories |
| Domain service | `DomainService` | Stateless cross-aggregate logic |
| Command | `Command` | Immutable request (DTO) a use case handles |
| Use case | `UseCase[C, R]` / `AsyncUseCase[C, R]` | Application entry point (`C` is a `Command`) |
| Errors / Result | `DomainError`, `Result` | Domain failures, as exceptions or in-band values |

## Quick tour

### Value objects — immutable, compared by value

Subclass `ValueObject` and declare fields; it becomes a frozen dataclass.

```python
from decimal import Decimal

from domino import ValueObject, DomainValidationError


class Money(ValueObject):
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise DomainValidationError("amount cannot be negative")


Money(Decimal("10"), "EUR") == Money(Decimal("10"), "EUR")  # True
Money(Decimal("10"), "EUR").replace(amount=Decimal("20"))  # a new instance
```

### Entities and aggregate roots

Subclass them and declare fields — an entity or aggregate becomes a mutable
dataclass with identity-based equality. An aggregate also records domain events;
you pull them out to publish after the transaction commits (no field to declare
for them — the base manages them).

```python
from dataclasses import field
from datetime import UTC, datetime

from domino import AggregateRoot, DomainEvent, DomainId, DomainStateError


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    # event_id and occurred_on are inherited and auto-filled


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


order = Order()
order.confirm()
events = order.pull_pending_events()  # [OrderConfirmed(...)]
```

### Event bus

```python
from domino import EventBus, EventHandler, DomainEvent


class NotifyWarehouse(EventHandler):
    def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            ...  # reserve stock


bus = EventBus()
bus.register(OrderConfirmed, NotifyWarehouse())  # many handlers per event allowed
bus.publish(*order.pull_pending_events())
```

Handlers are wrapped so a failing one is logged, never propagated to the caller
or the other handlers.

### Repository and unit of work

`Repository[T]` is a port you implement against your store. `UnitOfWork` is a
thin transaction boundary: it exposes repositories and commits on a clean exit,
rolls back on error. Wire the actual persistence through the `commit` /
`rollback` hooks (e.g. a SQLAlchemy session), and pass an `event_bus` to let the
unit of work publish domain events once the transaction is durable.

```python
from domino import UnitOfWork

uow = UnitOfWork(
    {"orders": order_repo},
    event_bus=bus,  # optional: publishes the queued events after commit
    commit=session.commit,
    rollback=session.rollback,
)

with uow:
    order = uow.orders.get_by_id(order_id)
    order.confirm()
    uow.orders.save(order)
    uow.enqueue_events(*order.pull_pending_events())  # published on commit
    # commit runs automatically here; rollback runs if the block raises
```

`AsyncRepository[T]` and `AsyncUnitOfWork` are the async twins: the same API,
awaited, driven with `async with`.

See [`examples/order_domain.py`](examples/order_domain.py) for a full,
runnable tour that wires every piece together.

### Persistence with SQLAlchemy (optional)

The core is dependency-free. An optional extra wires the infrastructure layer to
SQLAlchemy 2.0 via imperative mapping, so your aggregates stay pristine:

```bash
uv add "pydomino[sqlalchemy]"
```

```python
from domino.integrations.sqlalchemy import (
    DomainIdType,
    SqlAlchemyRepository,
    SqlAlchemyUnitOfWork,
)


class OrderRepository(
    SqlAlchemyRepository[Order]
):  # get_by_id / save / delete for free
    ...
```

Async works the same way — `AsyncSqlAlchemyRepository`, `AsyncSqlAlchemyUnitOfWork`
and `AsyncFilterable` over an `AsyncSession`. See the
[SQLAlchemy guide](docs/infrastructure/sqlalchemy.md),
[`examples/order_sqlalchemy.py`](examples/order_sqlalchemy.py) and
[`examples/order_sqlalchemy_async.py`](examples/order_sqlalchemy_async.py).

### Serving over HTTP with FastAPI (optional)

The `domino.integrations.fastapi` extra wires the presentation layer: a
per-request unit of work, a correlation id per request, `DomainError` → HTTP
status mapping, and domain-event dispatch after commit — one call to
`install_domino`. You pass a factory building the unit of work, so any
`UnitOfWork` / `AsyncUnitOfWork` works, not just the SQLAlchemy one.

```bash
uv add "pydomino[fastapi]" "domino[sqlalchemy]" aiosqlite
```

```python
from domino.integrations.fastapi import UnitOfWorkDep, install_domino
from domino.integrations.sqlalchemy import AsyncSqlAlchemyUnitOfWork

install_domino(
    app,
    # a factory: each request gets its own unit of work
    unit_of_work=lambda: AsyncSqlAlchemyUnitOfWork(
        session_factory=session_factory,
        repositories={"orders": OrderRepository},
        event_bus=bus,
    ),
)


@app.post("/orders", status_code=201)
async def place_order(body: PlaceOrderBody, uow: UnitOfWorkDep) -> dict[str, str]:
    async with uow:  # the transaction scope for this request
        order_id = await PlaceOrder(uow).execute(PlaceOrderCommand(...))
    return {"id": str(order_id)}
```

See the [FastAPI guide](docs/presentation/fastapi.md) and
[`examples/order_fastapi.py`](examples/order_fastapi.py).

### Correlation ids — automatic, no plumbing

Every use case runs inside an ambient correlation scope (a `contextvars`
context), and every `DomainEvent` captures that id when it is created. You never
pass it around: one id is generated per `execute` call and flows to every event
produced along the way, so you can trace a whole operation across logs and
handlers.

```python
class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    # the base __init__ takes the unit of work and exposes it as self._uow
    def execute(self, command: PlaceOrderCommand) -> DomainId:
        order = Order(customer_id=command.customer_id)
        order.confirm()  # the OrderConfirmed event captures the current id
        ...


# event.correlation_id is set automatically; get_correlation_id() reads it
```

A nested use case reuses the caller's id, and if the command carries a
`correlation_id` (e.g. from an upstream service) that trace is continued instead
of a new one being started. At other boundaries — web middleware, a message
consumer — open the scope yourself:

```python
from domino import correlation_scope

with correlation_scope(incoming_id):  # or no argument to generate one
    handle(message)
```

### Contextual logging — `self.log`

Use cases, event handlers and aggregate roots expose `self.log`, a logger that
stamps every line with the class doing the logging and the current correlation
id — no plumbing, no arguments to pass.

```python
class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    def execute(self, command: PlaceOrderCommand) -> DomainId:
        self.log.info("placing order for %s", command.customer_id)
        ...


# INFO domino [PlaceOrder] [cid=8f3e…] placing order for 7ff8…
```

The class and id are also attached to the record as `domino_context` and
`correlation_id` fields for structured handlers. Domino never configures logging
itself — enable it in your app (`logging.basicConfig(level="INFO")`) and tune the
`domino` logger. Mix `LoggerMixin` into your own classes to get the same
`self.log`, or call `get_logger("MyThing")` directly.

## Configuration

A few cross-cutting behaviours are tuned in one place. Call `configure(...)` once
at startup; only what you pass changes.

```python
from uuid import uuid4
from domino import configure

# 16-char correlation ids instead of a 32-char uuid hex
configure(correlation_id_factory=lambda: uuid4().hex[:16])

# or a third-party generator such as NanoID — for domain ids too
from nanoid import generate

configure(
    correlation_id_factory=lambda: generate(size=16),
    id_factory=generate,  # used by DomainId.generate()
)
```

`correlation_id_factory` feeds `new_correlation_id()` (hence every correlation
scope and `event.correlation_id`); `id_factory` feeds `DomainId.generate()`.
`get_config()` reads the current settings and `reset_config()` restores the
defaults (handy in tests).

## Documentation

Full documentation — a Domain-Driven Design primer and a build-with-Domino guide —
lives in [`docs/`](docs/index.md), built with MkDocs + Material:

```bash
uv sync --group docs     # install the docs toolchain
uv run mkdocs serve      # live preview at http://127.0.0.1:8000
uv run mkdocs gh-deploy  # publish to GitHub Pages
```

## Development

```bash
uv sync            # install dev dependencies (pytest, ruff, ty)
uv run pytest      # run the test suite
uv run ruff check  # lint
uv run ruff format # format
uv run ty check    # type-check
```

## Scope

`domino` currently covers the **tactical DDD** patterns and the *domain events*
pattern (an aggregate records events for you to publish). It is **not** an
event-sourcing framework — there is no event store and aggregates are not
rebuilt from an event stream. Event sourcing is a possible future addition.

Two integrations ship today, SQLAlchemy and FastAPI. What else could plug into
the same ports — brokers, other stores, tracing — and in which order it is worth
building, is laid out in the
[integration roadmap](docs/roadmap/integrations.md).
