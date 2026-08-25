# Tutorial: an order domain

This tutorial assembles everything into one small but complete bounded context —
an order-management domain — so you can see how the pieces fit. We build it in the
order you'd actually model it: value objects first, then the aggregate and its
events, then the ports, then the application layer, then the wiring.

A full runnable version lives in `examples/order_domain.py` in the repository;
this page walks through the same ideas.

## 1. Value objects

Start with the concepts that have no identity. `Money` carries its own rules.

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
            raise DomainValidationError("cannot add different currencies")
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, factor: int) -> "Money":
        return Money(self.amount * factor, self.currency)
```

## 2. Events

Name the meaningful things that happen, in the past tense. Inherited fields
(`event_id`, `occurred_on`, `correlation_id`) come for free.

```python
from domino import DomainEvent, DomainId


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    customer_id: DomainId
    total: str


class OrderShipped(DomainEvent):
    order_id: DomainId
```

## 3. The aggregate

`Order` is the consistency boundary. Every rule — you can't confirm an empty order,
you can't ship a draft — is enforced here, and callers can only reach the lines
through the root.

```python
from dataclasses import field
from datetime import UTC, datetime

from domino import AggregateRoot, DomainId, DomainStateError


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    customer_id: DomainId = field(default_factory=DomainId.generate)
    lines: list[dict] = field(default_factory=list)
    status: str = "draft"
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_line(self, product: str, quantity: int, unit_price: Money) -> None:
        if self.status != "draft":
            raise DomainStateError("cannot add lines to a non-draft order")
        self.lines.append({"product": product, "qty": quantity, "price": unit_price})
        self._touch()

    def total(self) -> Money:
        return sum(
            (line["price"] * line["qty"] for line in self.lines),
            Money(Decimal("0"), "EUR"),
        )

    def confirm(self) -> None:
        if self.status != "draft":
            raise DomainStateError("only draft orders can be confirmed")
        if not self.lines:
            raise DomainStateError("cannot confirm an empty order")
        self.status = "confirmed"
        self._touch()
        self.log.info("confirmed, total %s", self.total().amount)
        self._add_event(
            OrderConfirmed(
                order_id=self._id,
                customer_id=self.customer_id,
                total=str(self.total().amount),
            )
        )

    def ship(self) -> None:
        if self.status != "confirmed":
            raise DomainStateError("only confirmed orders can be shipped")
        self.status = "shipped"
        self._touch()
        self._add_event(OrderShipped(order_id=self._id))
```

## 4. The repository (a port)

The domain depends on this interface; infrastructure implements it. In-memory is
enough to run everything.

```python
from domino import Repository


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

## 5. Handlers

Consequences of events. Each gets `self.log` for free.

```python
from domino import DomainEvent, EventHandler


class ReserveStock(EventHandler):
    def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            self.log.info("reserving stock for order %s", event.order_id)


class SendConfirmationEmail(EventHandler):
    def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            self.log.info("emailing customer %s", event.customer_id)


class GenerateTracking(EventHandler):
    def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderShipped):
            self.log.info("tracking generated for order %s", event.order_id)
```

## 6. The application layer

A command and a use case per user goal. The use case only orchestrates.

```python
from domino import Command, EventBus, UnitOfWork, UseCase


class PlaceOrderCommand(Command):
    customer_id: DomainId
    items: list[tuple[str, int, Money]]


class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    # the base __init__ takes the unit of work; reach the repositories through it

    def execute(self, command: PlaceOrderCommand) -> DomainId:
        self.log.info("placing order for %s", command.customer_id)
        orders = self._uow.repository("orders")
        order = Order(customer_id=command.customer_id)
        for product, qty, price in command.items:
            order.add_line(product, qty, price)
        order.confirm()
        orders.save(order)
        self._uow.enqueue_events(*order.pull_pending_events())
        return order.id
```

## 7. Wiring it up

```python
import logging
from decimal import Decimal

logging.basicConfig(level=logging.INFO, format="%(levelname)-5s %(message)s")

orders = OrderRepository()
bus = EventBus()
bus.register_all(
    [
        (OrderConfirmed, ReserveStock()),
        (OrderConfirmed, SendConfirmationEmail()),
        (OrderShipped, GenerateTracking()),
    ]
)
uow = UnitOfWork({"orders": orders}, event_bus=bus)

with uow:  # the transaction scope; queued events are published after commit
    order_id = PlaceOrder(uow).execute(
        PlaceOrderCommand(
            customer_id=DomainId.generate(),
            items=[("Keyboard", 1, Money(Decimal("150"), "EUR"))],
        )
    )
```

Output — notice every line carries the class and a **shared** correlation id,
without a single line of plumbing:

```
INFO  [PlaceOrder] [cid=b1eb7a…] placing order for 1f7f8c…
INFO  [Order] [cid=b1eb7a…] confirmed, total 150
INFO  [ReserveStock] [cid=b1eb7a…] reserving stock for order 6d6019…
INFO  [SendConfirmationEmail] [cid=b1eb7a…] emailing customer 1f7f8c…
```

The two `OrderConfirmed` handlers share one id because they belong to the same
`PlaceOrder` call. A later `ShipOrder` use case would show a **different** id — a
new operation, a new trace.

## What you built

- A **domain layer** (`Money`, `Order`, the events) with all the rules inside it.
- An **application layer** (`PlaceOrderCommand`, `PlaceOrder`) that only orchestrates.
- **Infrastructure** (the repository, the bus wiring).
- **Observability** (correlation ids + `self.log`) for free.

From here: split each part into its own module along the [layered
structure](../ddd/layering.md), or let Domino [scaffold that structure
for you](../reference/scaffolding.md).
