# domino

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
uv add domino
# or, from a checkout:
uv pip install -e .
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
| Repository | `Repository[T]` | Collection-like persistence port |
| Unit of work | `UnitOfWork` | Transactional boundary around repositories |
| Domain service | `DomainService` | Stateless cross-aggregate logic |
| Command | `Command` | Immutable request (DTO) a use case handles |
| Use case | `UseCase[C, R]` | Application entry point (`C` is a `Command`) |
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
`rollback` hooks (e.g. a SQLAlchemy session).

```python
from domino import UnitOfWork

uow = UnitOfWork(
    {"orders": order_repo}, commit=session.commit, rollback=session.rollback
)

with uow:
    order = uow.orders.get_by_id(order_id)
    order.confirm()
    uow.orders.save(order)
    # commit runs automatically here; rollback runs if the block raises
```

See [`examples/order_domain.py`](examples/order_domain.py) for a full,
runnable tour that wires every piece together.

### Correlation ids — automatic, no plumbing

Every use case runs inside an ambient correlation scope (a `contextvars`
context), and every `DomainEvent` captures that id when it is created. You never
pass it around: one id is generated per `execute` call and flows to every event
produced along the way, so you can trace a whole operation across logs and
handlers.

```python
class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
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
