# Domino API cheat-sheet

Compact reference. Everything is importable from the top-level `domino` package.
Remember the golden rule: **subclass a base, declare fields, no `@dataclass`.**

## Core

### `DomainId`
A typed identifier wrapping a `UUID` (default) or a `str`.
```python
DomainId.generate()  # new id (uuid4 by default; see configure)
DomainId("ORD-2024-001")  # string-based id
DomainId.empty()  # "not yet assigned" sentinel
d.value  # -> UUID | str
d.is_empty()  # -> bool
```

### `Entity`
Identity-based base. Declare `_id`; equality/hash come from the id.
```python
class Customer(Entity):
    _id: DomainId = field(default_factory=DomainId.generate)
    name: str = ""


c.id  # -> DomainId
c.is_transient()  # True if id is empty
```

### `ValueObject`
Frozen, value-compared. Validate in `__post_init__`.
```python
class Money(ValueObject):
    amount: Decimal
    currency: str


m.replace(amount=Decimal("5"))  # new instance with changes
```

### Errors — `DomainError` and subclasses
```python
DomainError(message, code=None)  # base; .message, .code (defaults to class name)
DomainValidationError(...)  # code "VALIDATION_ERROR" — bad input
DomainStateError(...)  # code "STATE_ERROR" — invalid transition
DomainNotFoundError(...)  # code "NOT_FOUND" — missing aggregate
```

### `Result` — in-band success/failure (optional)
```python
from domino import success, failure, Success, Failure, Result

success(value)  # Success
failure(domain_error)  # Failure
r.is_success() / r.is_failure()
r.map(fn) / r.map_error(fn) / r.bind(fn)
r.unwrap()  # value, or raises the error
r.unwrap_or(default) / r.unwrap_or_else(fn)
r.unwrap_error()  # the error (raises on Success)
```
Prefer raising `DomainError` for real invariant violations; use `Result` for
expected outcomes (a lookup that may miss).

## Aggregate & events

### `AggregateRoot`
An `Entity` that records events. No field needed for pending events.
```python
class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def confirm(self):
        self._touch()  # refresh updated_at (needs the field)
        self._add_event(OrderConfirmed(order_id=self._id))


o.pull_pending_events()  # -> list[DomainEvent], and clears them (call once)
o.has_pending_events()  # -> bool
```

### `DomainEvent`
Frozen, keyword-only. `event_id: UUID`, `occurred_on: datetime`,
`correlation_id: str | None` are inherited and auto-filled — **do not redeclare**.
```python
class OrderConfirmed(DomainEvent):
    order_id: DomainId
    total: str


e = OrderConfirmed(order_id=..., total="42.00")  # keyword args only
e.event_name  # -> "OrderConfirmed"
e.event_id, e.occurred_on, e.correlation_id
```

### `EventPublisher` / `EventBus` / `EventHandler`
```python
class InventoryHandler(EventHandler):
    def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            ...


bus = EventBus()
bus.register(OrderConfirmed, InventoryHandler())  # many handlers per event ok
bus.register_all(
    [(OrderConfirmed, h1), (OrderShipped, h2)]
)  # pairs or a {type: handler} mapping
bus.publish(*aggregate.pull_pending_events())
bus.handler_count(OrderConfirmed)  # or handler_count() for the total
bus.clear()
# SafeEventHandler wraps a handler so its errors are logged, not propagated
# (register() wraps handlers for you).
```

## Persistence & transactions

### `Repository[T]`  (T bound to Entity)
Implement against your store; one repository per aggregate type.
```python
class OrderRepository(Repository[Order]):
    def get_by_id(self, id: DomainId) -> Order | None: ...
    def save(self, aggregate: Order) -> None: ...
    def delete(self, id: DomainId) -> None: ...
```

### `UnitOfWork`
Thin transaction boundary + repository registry. No change tracking.
```python
uow = UnitOfWork(
    {"orders": order_repo},
    commit=session.commit,  # optional hooks; default no-ops
    rollback=session.rollback,
)
uow.orders  # attribute access to a repository
uow.repository("orders")  # or by name
uow.register("customers", repo)  # add one later

with uow:  # commit on clean exit, rollback on exception
    uow.orders.save(order)
    # uow.commit() explicitly is fine too (idempotent within the scope)
```

## Application layer

### `Command`
Immutable input DTO.
```python
class PlaceOrderCommand(Command):
    customer_id: DomainId
    items: list[tuple[str, int]]
```

### `UseCase[C, R]`  (C bound to Command)
One user goal. Implement `execute`; it auto-runs in a correlation scope.
```python
class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    def execute(self, command: PlaceOrderCommand) -> DomainId:
        self.log.info("placing order")  # self.log is available
        ...
        return order.id
```

### `DomainService`
Marker base for stateless cross-aggregate logic (no auto-dataclass; plain class).
```python
class TransferService(DomainService):
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts
```

## Cross-cutting

### Correlation (`contextvars`)
```python
from domino import correlation_scope, get_correlation_id, new_correlation_id

get_correlation_id()  # -> str | None (current scope's id)
with correlation_scope(cid=None) as cid:  # generates one if not given
    ...
```
Use cases open a scope automatically; events capture `correlation_id` on creation.

### Logging
```python
from domino import get_logger, LoggerMixin, DominoLogger

self.log.info("msg %s", arg)  # on UseCase / EventHandler / AggregateRoot
get_logger("MyThing").info(...)  # anywhere


class MyRepo(Repository[X], LoggerMixin): ...  # add self.log to your own class


# Record extra fields: record.correlation_id, record.domino_context
```

### Configuration
```python
from domino import configure, get_config, reset_config, DominoConfig

configure(
    correlation_id_factory=lambda: ..., id_factory=lambda: ...
)  # partial; call once
get_config()  # -> DominoConfig snapshot
reset_config()  # restore defaults (tests)
```
