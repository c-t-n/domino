# Repositories & unit of work

The domain layer must never see a database. [Repositories](../ddd/building-blocks.md#repositories)
give it a collection-like way to load and store aggregates, and the [unit of
work](../ddd/building-blocks.md#unit-of-work) defines the transaction around those
changes.

## Repository: a port the domain owns

`Repository[T]` is an abstract interface (a *port*) for one aggregate type. You
declare it near the domain and *implement* it in infrastructure. The three
operations deal in whole aggregates, keyed by identity:

```python
from domino import Repository, DomainId


class OrderRepository(Repository[Order]):
    def get_by_id(self, id: DomainId) -> Order | None: ...
    def save(self, aggregate: Order) -> None: ...
    def delete(self, id: DomainId) -> None: ...
```

An in-memory implementation is all you need for tests and early development:

```python
class InMemoryOrderRepository(OrderRepository):
    def __init__(self) -> None:
        self._store: dict[DomainId, Order] = {}

    def get_by_id(self, id: DomainId) -> Order | None:
        return self._store.get(id)

    def save(self, aggregate: Order) -> None:
        self._store[aggregate.id] = aggregate

    def delete(self, id: DomainId) -> None:
        self._store.pop(id, None)
```

For an async stack, implement `AsyncRepository[T]` instead — the same three
operations, declared `async`:

```python
from domino import AsyncRepository, DomainId


class OrderRepository(AsyncRepository[Order]):
    async def get_by_id(self, id: DomainId) -> Order | None: ...
    async def save(self, aggregate: Order) -> None: ...
    async def delete(self, id: DomainId) -> None: ...
```

A real one (SQLAlchemy, a document store, …) has the same signature; only the body
changes. Because the application layer depends on the `OrderRepository` *interface*,
you can swap the implementation without touching a use case — and test against the
in-memory one.

!!! tip "Return whole aggregates"
    A repository returns a fully-formed `Order`, not a row or a DTO. Queries that
    span aggregates or return read-optimised shapes aren't repository methods —
    they belong in a separate query/read service.

## Unit of work: the transaction boundary

`UnitOfWork` is a thin boundary that exposes your repositories and commits on a
clean exit, rolling back on an exception. It deliberately does **not** track your
changes — you save through the repository yourself.

```python
from domino import UnitOfWork

uow = UnitOfWork({"orders": order_repo})

with uow:
    order = uow.orders.get_by_id(order_id)  # attribute access to a repository
    order.confirm()
    uow.orders.save(order)
    # commit runs automatically here; rollback runs if the block raises
```

Repositories are reachable both as attributes (`uow.orders`) and by name
(`uow.repository("orders")`), and you can add one later with `uow.register(...)`.

### Wiring a real database

Pass `commit` / `rollback` hooks and Domino drives your session's transaction at the
scope boundary:

```python
uow = UnitOfWork(
    {"orders": order_repo},
    commit=session.commit,
    rollback=session.rollback,
)
```

With an in-memory store that writes on `save`, the hooks default to no-ops, so the
same code path works in tests and in production. Calling `uow.commit()` explicitly
inside the block is fine too — it's idempotent within a scope, so the automatic
commit on exit won't double-fire.

### Publishing domain events on commit

Give the unit of work an `event_bus` and queue the aggregates' events with
`enqueue_events(...)`. They are published **after** the commit succeeds — never
when the scope rolls back:

```python
uow = UnitOfWork({"orders": order_repo}, event_bus=bus)

with uow:
    order.ship()
    uow.orders.save(order)
    uow.enqueue_events(*order.pull_pending_events())
    # commit runs on exit, then the queued events go to the bus
```

The queue is explicit on purpose: you decide which events leave the transaction,
and a use case never has to hold a reference to the bus.

The queue belongs to the **scope**, not to the unit of work: it is emptied when
the block exits, whether it committed or rolled back. Reusing the same unit of
work for a later transaction therefore never replays the previous scope's
events.

### The async unit of work

`AsyncUnitOfWork` is the twin for an async stack — same constructor, same
repository access and the same `enqueue_events`, but driven with `async with` and
awaited `commit()` / `rollback()`:

```python
from domino import AsyncUnitOfWork

uow = AsyncUnitOfWork({"orders": order_repo}, event_bus=bus)

async with uow:
    order = await uow.orders.get_by_id(order_id)
    order.confirm()
    await uow.orders.save(order)
    uow.enqueue_events(*order.pull_pending_events())
```

It holds `AsyncRepository` implementations, and the
[SQLAlchemy integration](../infrastructure/sqlalchemy.md#async) subclasses it.

## The shape of a persisted operation

Putting it together, a typical write looks like this — load, change, save inside the
unit of work, queue the events for after the commit:

```python
with uow:
    order = uow.orders.get_by_id(command.order_id)
    if order is None:
        raise DomainNotFoundError(f"order {command.order_id} not found")
    order.ship()
    uow.orders.save(order)
    uow.enqueue_events(*order.pull_pending_events())
```

Without an `event_bus` on the unit of work, publish them yourself once the scope
has exited — after commit, never inside it:

```python
bus.publish(*order.pull_pending_events())
```

---

Next: [Commands & use cases →](use-cases.md)
