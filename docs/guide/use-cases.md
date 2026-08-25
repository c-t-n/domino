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

The base constructor takes the [unit of work](persistence.md) and exposes it as
`self._uow`, so a use case reaches its repositories through it — no separate
repository or bus to inject:

```python
from domino import DomainId, UnitOfWork, UseCase


class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    # __init__(self, uow: UnitOfWork) comes from the base class

    def execute(self, command: PlaceOrderCommand) -> DomainId:
        self.log.info("placing order for %s", command.customer_id)
        orders = self._uow.repository("orders")  # or self._uow.orders

        order = Order.place(command.customer_id)  # domain decides
        for product, qty, price in command.items:
            order.add_line(product, qty, Money(price, "EUR"))
        order.confirm()

        orders.save(order)
        self._uow.enqueue_events(*order.pull_pending_events())  # sent after commit
        return order.id
```

The transaction scope is a `with` block on that same unit of work. Open it inside
`execute` when the use case owns the transaction, or let the caller open it — a
route, a CLI command, another use case — and pass the live unit of work in:

```python
with uow:
    order_id = PlaceOrder(uow).execute(command)
```

A use case does four things and no more:

1. **Validate / accept input** (the command).
2. **Drive the domain** — load aggregates, call their methods, let *them* enforce
   the rules.
3. **Manage the transaction** via the unit of work.
4. **Return a result** (an id, a DTO) and queue the events to publish.

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

### Async use cases

For an async stack (FastAPI, the async SQLAlchemy unit of work), subclass
`AsyncUseCase[C, R]` instead — identical, but it takes an `AsyncUnitOfWork` and
`execute` is a coroutine:

```python
from domino import AsyncUseCase, DomainId


class PlaceOrder(AsyncUseCase[PlaceOrderCommand, DomainId]):
    # __init__(self, uow: AsyncUnitOfWork) comes from the base class

    async def execute(self, command: PlaceOrderCommand) -> DomainId:
        order = Order.place(command.customer_id)
        await self._uow.orders.save(order)
        self._uow.enqueue_events(*order.pull_pending_events())
        return order.id
```

Called under a scope the presentation layer opens:

```python
async with uow:
    order_id = await PlaceOrder(uow).execute(command)
```

The same automatic correlation scope applies, and it **reuses** an upstream scope
when one is active — so behind the [FastAPI integration](../presentation/fastapi.md)'s
correlation middleware, the whole request shares one id. Passing an `event_bus` to
the unit of work lets it publish the queued events for you after commit, so an
async use case needn't call the bus itself.

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
