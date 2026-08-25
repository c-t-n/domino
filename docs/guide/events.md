# Domain events

A [domain event](../ddd/building-blocks.md#domain-events) is an immutable record of
something that happened. In Domino, aggregates *record* events; an **event bus**
*routes* them to **handlers** that react.

## Defining an event

Subclass `DomainEvent` and declare the payload. Every event inherits three fields
that are **filled in automatically — never redeclare them**:

- `event_id: UUID` — a unique id for this occurrence
- `occurred_on: datetime` — when it happened (UTC)
- `correlation_id: str | None` — the ambient [correlation id](observability.md)

```python
from domino import DomainEvent, DomainId


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    customer_id: DomainId
    total: str


event = OrderConfirmed(order_id=..., customer_id=..., total="42.00")
event.event_name  # "OrderConfirmed"
event.event_id  # auto-filled UUID
event.correlation_id  # captured from the current operation
```

Events are frozen and keyword-only. Keyword-only is what lets your fields sit after
the base's defaulted ones without a dataclass ordering error — so you write your
payload naturally and never touch the inherited fields.

!!! tip "Name them in the past tense"
    `OrderConfirmed`, `PaymentFailed`, `StockReserved`. An event is a fact about the
    past; the name should read like one.

## Handlers

A handler reacts to an event — the *consequence*, not the primary action. Subclass
`EventHandler` and implement `handle`, guarding on the event type you care about:

```python
from domino import DomainEvent, EventHandler


class ReserveStock(EventHandler):
    def __init__(self, warehouse) -> None:
        self._warehouse = warehouse

    def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            self.log.info("reserving stock for %s", event.order_id)
            self._warehouse.reserve(event.order_id)
```

Handlers get `self.log` for free (see [logging](observability.md)). Keep them
focused: one consequence per handler reads best.

## The event bus

`EventBus` routes events to registered handlers, in memory:

```python
from domino import EventBus

bus = EventBus()
bus.register(OrderConfirmed, ReserveStock(warehouse))
bus.register(OrderConfirmed, SendConfirmationEmail(mailer))  # many handlers per event
bus.register(OrderShipped, GenerateTrackingNumber())

# or register several at once, from pairs or a mapping:
bus.register_all(
    [
        (OrderConfirmed, ReserveStock(warehouse)),
        (OrderShipped, GenerateTrackingNumber()),
    ]
)

bus.publish(*order.pull_pending_events())
```

Every handler is wrapped so that a failing one is **logged, never propagated** —
one broken handler can't stop the others or bubble an exception back to the caller.
(That wrapper is `SafeEventHandler`; `register` applies it for you.)

## Publish after the commit

The standard flow: an aggregate records events during a use case, and they are
**published after the transaction commits**. Hand the unit of work an `event_bus`
and queue them with `enqueue_events(...)`; it publishes them once the commit
succeeds, and drops them if the scope rolls back.

```python
uow = UnitOfWork({"orders": orders}, event_bus=bus)


def execute(self, command) -> None:
    order = self._uow.orders.get_by_id(command.order_id)
    order.confirm()
    self._uow.orders.save(order)
    self._uow.enqueue_events(*order.pull_pending_events())  # <- sent after commit
```

Without an `event_bus`, publish them yourself once the scope has exited:

```python
with uow:
    orders.save(order)
bus.publish(*order.pull_pending_events())  # <- after commit
```

Publishing after the commit matters: a handler that sends an email or calls another
service should only run if the change actually persisted. `pull_pending_events()`
returns the events and clears them, so call it once — and the unit of work clears
its own queue when the scope exits, so nothing is replayed by a later transaction.

!!! note "In-memory, synchronous"
    Domino's `EventBus` dispatches synchronously in the current process — perfect
    for handlers that must run in the same request, and for tests. For
    cross-service delivery, implement the [`EventPublisher`](../reference/cheatsheet.md)
    interface against your broker and publish there instead.

---

Next: [Repositories & unit of work →](persistence.md)
