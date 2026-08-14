# API cheat-sheet

Compact reference for every building block. Everything is importable from the
top-level `domino` package. The golden rule holds throughout: **subclass a base,
declare fields, never add `@dataclass`.**

## Core

### `DomainId`

```python
DomainId.generate()  # new id (uuid4 by default; see configure())
DomainId("ORD-2024-001")  # string-based id
DomainId.empty()  # "not yet assigned" sentinel
d.value  # -> UUID | str
d.is_empty()  # -> bool
```

### `Entity`

```python
class Customer(Entity):
    _id: DomainId = field(default_factory=DomainId.generate)
    name: str = ""


c.id  # -> DomainId
c.is_transient()  # True if the id is empty
```

### `ValueObject`

```python
class Money(ValueObject):
    amount: Decimal
    currency: str


m.replace(amount=Decimal("5"))  # new instance with changes
```

### Errors

```python
DomainError(message, code=None)  # base; .message, .code (defaults to class name)
DomainValidationError(...)  # code "VALIDATION_ERROR" — bad input
DomainStateError(...)  # code "STATE_ERROR" — invalid transition
DomainNotFoundError(...)  # code "NOT_FOUND" — missing aggregate
```

### `Result` (optional, in-band success/failure)

```python
from domino import success, failure, Success, Failure, Result

success(value)
failure(error)
r.is_success() / r.is_failure()
r.map(fn) / r.map_error(fn) / r.bind(fn)
r.unwrap() / r.unwrap_or(default) / r.unwrap_or_else(fn) / r.unwrap_error()
```

Prefer raising `DomainError` for real invariant violations; use `Result` for
expected outcomes (a lookup that may miss).

## Aggregate & events

### `AggregateRoot`

```python
class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def confirm(self):
        self._touch()  # refresh updated_at (needs the field)
        self._add_event(OrderConfirmed(order_id=self._id))


o.pull_pending_events()  # -> list[DomainEvent], clears them (call once)
o.has_pending_events()  # -> bool
```

### `DomainEvent`

```python
class OrderConfirmed(DomainEvent):
    order_id: DomainId
    total: str


# inherited & auto-filled — never redeclare: event_id, occurred_on, correlation_id
e.event_name  # -> class name
```

### `EventBus` / `EventHandler`

```python
bus = EventBus()
bus.register(OrderConfirmed, handler)  # many handlers per event allowed
bus.register_all([(OrderConfirmed, h1), ...])  # pairs or {type: handler} mapping
bus.publish(*aggregate.pull_pending_events())
bus.handler_count(OrderConfirmed)  # or handler_count() total
bus.clear()
```

Handlers are wrapped in `SafeEventHandler` so errors are logged, not propagated.

## Persistence

### `Repository[T]`

```python
class OrderRepository(Repository[Order]):
    def get_by_id(self, id: DomainId) -> Order | None: ...
    def save(self, aggregate: Order) -> None: ...
    def delete(self, id: DomainId) -> None: ...
```

### `UnitOfWork`

```python
uow = UnitOfWork({"orders": repo}, commit=session.commit, rollback=session.rollback)
uow.orders  # attribute access
uow.repository("orders")  # by name
uow.register("customers", r)  # add later

with uow:  # commit on clean exit, rollback on exception
    uow.orders.save(order)
```

## Specifications

Composable, persistence-ignorant filter criteria.

```python
from domino import eq, ne, lt, le, gt, ge, in_, like, Specification

eq("status", "active")
gt("age", 18)
in_("tier", ["a", "b"])
like("name", "AC-%")
spec = eq("status", "active") & gt("age", 18)  # & | ~ compose
spec.is_satisfied_by(candidate)  # -> bool (in memory)

# with domino.integrations.sqlalchemy.Filterable, the same specs query the database:
repo.list(eq("status", "active"), gt("age", 18))  # positional args are AND-ed
```

## Application

### `Command` / `UseCase[C, R]`

```python
class PlaceOrderCommand(Command):
    customer_id: DomainId


class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    def execute(self, command: PlaceOrderCommand) -> DomainId:
        self.log.info("placing order")  # self.log available
        ...


# Async stack (FastAPI, async SQLAlchemy): same, but execute is a coroutine
class PlaceOrder(AsyncUseCase[PlaceOrderCommand, DomainId]):
    async def execute(self, command: PlaceOrderCommand) -> DomainId: ...
```

### `DomainService`

```python
class TransferService(DomainService):  # plain marker base (no auto-dataclass)
    ...
```

## Cross-cutting

### Correlation

```python
from domino import correlation_scope, get_correlation_id, new_correlation_id

get_correlation_id()  # -> str | None
with correlation_scope(cid=None):  # generates one if not given
    ...
```

### Logging

```python
from domino import get_logger, LoggerMixin, DominoLogger

self.log.info("msg %s", arg)  # on UseCase / EventHandler / AggregateRoot
get_logger("MyThing").info(...)  # anywhere


class MyRepo(Repository[X], LoggerMixin): ...  # add self.log to your own class
```

### Configuration

```python
from domino import configure, get_config, reset_config, DominoConfig

configure(correlation_id_factory=..., id_factory=...)  # partial; call once
get_config()
reset_config()
```
