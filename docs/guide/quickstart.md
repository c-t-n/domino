# Quickstart

This page builds a tiny but complete slice — an aggregate that emits an event, a
handler that reacts, and a use case that drives it — in about five minutes. Later
pages take each piece apart.

## Install

```bash
uv add domino
# or: pip install domino
```

## The one rule to remember

Domino base classes apply the right `@dataclass` for you (via
[PEP 681](https://peps.python.org/pep-0681/) `@dataclass_transform`, so type
checkers still see the generated `__init__`). **You subclass a base and declare
fields — you never add `@dataclass` yourself.**

```python
from domino import ValueObject


class Money(ValueObject):  # ✅
    amount: int
    currency: str
```

```python
from dataclasses import dataclass
from domino import ValueObject


@dataclass(frozen=True)  # ❌ don't — the base already does this
class Money(ValueObject):
    amount: int
    currency: str
```

## A complete slice

```python
from dataclasses import field
from datetime import UTC, datetime

from domino import (
    AggregateRoot,
    Command,
    DomainEvent,
    DomainId,
    DomainStateError,
    EventBus,
    EventHandler,
    UnitOfWork,
    UseCase,
    Repository,
)


# --- Domain -----------------------------------------------------------------


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    # event_id, occurred_on and correlation_id are inherited and auto-filled


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


# --- Infrastructure ---------------------------------------------------------


class OrderRepository(Repository[Order]):
    def __init__(self) -> None:
        self._store: dict[DomainId, Order] = {}

    def get_by_id(self, id: DomainId) -> Order | None:
        return self._store.get(id)

    def save(self, aggregate: Order) -> None:
        self._store[aggregate.id] = aggregate

    def delete(self, id: DomainId) -> None:
        self._store.pop(id, None)


class WhenOrderConfirmed(EventHandler):
    def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            self.log.info("reserving stock for %s", event.order_id)


# --- Application ------------------------------------------------------------


class PlaceOrderCommand(Command):
    pass


class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    # the base __init__ takes the unit of work and stores it as self._uow

    def execute(self, command: PlaceOrderCommand) -> DomainId:
        order = Order()
        order.confirm()
        self._uow.orders.save(order)
        self._uow.enqueue_events(*order.pull_pending_events())  # sent AFTER commit
        return order.id


# --- Wiring -----------------------------------------------------------------

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

orders = OrderRepository()
bus = EventBus()
bus.register(OrderConfirmed, WhenOrderConfirmed())

uow = UnitOfWork({"orders": orders}, event_bus=bus)

with uow:  # commit on success, rollback on error; queued events publish after
    order_id = PlaceOrder(uow).execute(PlaceOrderCommand())
print("order:", orders.get_by_id(order_id).status)
```

Running it prints something like:

```
INFO [WhenOrderConfirmed] [cid=8f3e…] reserving stock for 1f7f…
order: confirmed
```

Notice two things you never wired up: the handler's log line already carries the
class name and a **correlation id** — both propagated automatically. That's the
subject of [Correlation ids & logging](observability.md).

## Where to go next

- [Value objects](value-objects.md) · [Entities & aggregates](entities-aggregates.md)
- [Domain events](events.md) · [Repositories & unit of work](persistence.md)
- [Commands & use cases](use-cases.md)
- The full [Order domain tutorial](../tutorial/order-domain.md)
