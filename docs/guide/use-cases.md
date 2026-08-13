# Commands & use cases

The domain models the business; the **application layer** drives it from the
outside. A [command](../ddd/building-blocks.md#commands-and-use-cases) is the input,
a **use case** handles it, and both are thin — the domain still makes every
decision.

## Commands

A `Command` is an immutable DTO describing an intent. Subclass it and declare the
inputs (no `@dataclass` — it becomes a frozen dataclass for you):

```python
from decimal import Decimal
from domino import Command, DomainId


class PlaceOrderCommand(Command):
    customer_id: DomainId
    items: list[tuple[str, int, Decimal]]
```

A command carries *data*, not behaviour. It's the shape your HTTP or CLI layer
builds and hands to a use case.

## Use cases

`UseCase[C, R]` is generic over its command type `C` (bound to `Command`) and its
result type `R`. Implement `execute`; that's the one entry point for one user goal.

```python
from domino import DomainId, EventBus, UnitOfWork, UseCase


class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    def __init__(self, orders: OrderRepository, uow: UnitOfWork, bus: EventBus) -> None:
        self._orders = orders
        self._uow = uow
        self._bus = bus

    def execute(self, command: PlaceOrderCommand) -> DomainId:
        self.log.info("placing order for %s", command.customer_id)

        order = Order.place(command.customer_id)  # domain decides
        for product, qty, price in command.items:
            order.add_line(product, qty, Money(price, "EUR"))
        order.confirm()

        with self._uow:  # transaction boundary
            self._orders.save(order)

        self._bus.publish(*order.pull_pending_events())  # publish after commit
        return order.id
```

A use case does four things and no more:

1. **Validate / accept input** (the command).
2. **Drive the domain** — load aggregates, call their methods, let *them* enforce
   the rules.
3. **Manage the transaction** via the unit of work.
4. **Return a result** (an id, a DTO) and publish events.

!!! danger "No business logic in the use case"
    If you find an `if`-statement enforcing a business rule inside `execute`, it's
    in the wrong place — move it onto the aggregate (or a domain service). The use
    case orchestrates; the domain decides. Keeping this line clean is what keeps the
    model rich instead of anemic.

### Automatic correlation scope

Every `execute` call runs inside a [correlation scope](observability.md): a
correlation id is generated once per call and captured by every domain event and
log line produced along the way. You don't wire anything up — see
[Correlation ids & logging](observability.md).

## Domain services

Most logic has a natural home on an entity or value object. Occasionally a rule
genuinely spans **several aggregates** and belongs to none — a funds transfer
touches two accounts. That goes in a **domain service**: a stateless object, named
after a domain concept, living in the **domain** layer (unlike a use case, it has no
transactions, auth or logging concerns).

```python
from domino import DomainService, DomainStateError


class TransferService(DomainService):
    def transfer(self, source: Account, target: Account, amount: Money) -> None:
        source.withdraw(amount)  # each aggregate still enforces its own rules
        target.deposit(amount)
```

`DomainService` is a plain marker base (no auto-dataclass). Reach for it *only* when
the logic has no natural home on an aggregate — over-using it drains behaviour out
of your model and back toward an anemic design.

---

Next: [Correlation ids & logging →](observability.md)
