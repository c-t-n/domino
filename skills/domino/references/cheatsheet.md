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
        self._touch()  # refresh updated_at (no-op without the field)
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

### `AsyncEventBus` / `AsyncEventPublisher`

```python
class NotifyWarehouse(AsyncEventHandler):
    async def handle(self, event: DomainEvent) -> None: ...


bus = AsyncEventBus()
bus.register(OrderConfirmed, NotifyWarehouse())  # sync handlers accepted too
await bus.publish(*order.pull_pending_events())
```

Handlers run in registration order, failures stay isolated. `AsyncUnitOfWork`
accepts either publisher: it awaits `publish` only when it returns an awaitable.

### Transactional outbox (SQLAlchemy)

```python
outbox = Outbox(registry, metadata=metadata)  # declares `domino_outbox`
uow = AsyncSqlAlchemyUnitOfWork(session_factory, repos, outbox=outbox)
# enqueue_events(...) now commits with the rows, instead of publishing directly

relay = AsyncOutboxRelay(session_factory, outbox, publisher=broker)
await relay.run_once()  # or run(poll_interval=1.0)
relay.purge(older_than=timedelta(days=7))  # drop old *published* lines
```

At-least-once: consumers deduplicate on `event_id`. A failure stops the batch,
keeping order; `attempts` and `last_error` record why.

### Redis Streams (`pydomino[redis]`)

```python
publisher = AsyncRedisStreamPublisher(client, registry, stream="orders", maxlen=10_000)
relay = AsyncOutboxRelay(session_factory, outbox, publisher=publisher)

consumer = AsyncRedisStreamConsumer(
    client,
    registry,
    bus=bus,
    group="warehouse",
    consumer="worker-1",
    dedupe_ttl=timedelta(hours=24),  # skip an event_id already handled
)
await consumer.ensure_group()
await consumer.run()  # or run_once()
```

Each message reopens the producer's correlation scope. An entry is acked after
dispatch; one that cannot be decoded is logged and left pending, never dropped.

### `EventRegistry` — events across a process boundary

```python
registry = EventRegistry()
registry.register(OrderConfirmed)  # explicit; name= to namespace or version
registry.register_codec(IPv4Address, str, IPv4Address)  # unknown value types

envelope = registry.encode(event)  # event_name/event_id/occurred_on/
registry.decode(envelope)  # correlation_id/payload
registry.encode_json(event)  # and decode_json(raw)
```

Decimals keep their precision, value objects and entities are walked
recursively, unknown payload keys are ignored on decode. Failures raise
`SerializationError` — not a `DomainError`.

## Persistence & transactions

### `Repository[T]` / `AsyncRepository[T]`  (T bound to Entity)
Implement against your store; one repository per aggregate type. The async twin
has the same three operations, declared `async`.
```python
class OrderRepository(Repository[Order]):
    def get_by_id(self, id: DomainId) -> Order | None: ...
    def save(self, aggregate: Order) -> None: ...
    def delete(self, id: DomainId) -> None: ...


class OrderRepository(AsyncRepository[Order]):
    async def get_by_id(self, id: DomainId) -> Order | None: ...
    async def save(self, aggregate: Order) -> None: ...
    async def delete(self, id: DomainId) -> None: ...
```

### `UnitOfWork` / `AsyncUnitOfWork`
Thin transaction boundary + repository registry. No change tracking.
```python
uow = UnitOfWork(
    {"orders": order_repo},
    event_bus=bus,  # optional: publishes the queued events after commit
    commit=session.commit,  # optional hooks; default no-ops
    rollback=session.rollback,
)
uow.orders  # attribute access to a repository
uow.repository("orders")  # or by name
uow.register("customers", repo)  # add one later

with uow:  # commit on clean exit, rollback on exception
    uow.orders.save(order)
    uow.enqueue_events(*order.pull_pending_events())  # published after commit
    # the queue is per-scope: dropped on rollback, cleared on exit
    # uow.commit() explicitly is fine too (idempotent within the scope)

# AsyncUnitOfWork: same API over AsyncRepository[T], driven with `async with`
async with async_uow:
    await async_uow.orders.save(order)
    async_uow.enqueue_events(*order.pull_pending_events())
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
One user goal. The base `__init__` takes the unit of work and exposes it as
`self._uow`. Implement `execute`; it auto-runs in a correlation scope.
```python
class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    def execute(self, command: PlaceOrderCommand) -> DomainId:
        self.log.info("placing order")  # self.log is available
        self._uow.orders.save(order)
        self._uow.enqueue_events(*order.pull_pending_events())
        return order.id


with uow:  # the caller owns the scope (or open `with self._uow:` inside execute)
    order_id = PlaceOrder(uow).execute(command)
```
`AsyncUseCase[C, R]` is the same over an `AsyncUnitOfWork`, with `async def
execute`.

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
