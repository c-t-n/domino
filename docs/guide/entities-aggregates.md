# Entities & aggregates

Where value objects are defined by their attributes, [entities and
aggregates](../ddd/building-blocks.md#entities) are defined by **identity** and
have a **lifecycle**. Subclass `Entity` or `AggregateRoot` and declare fields — you
get a **mutable dataclass with identity-based equality** (again, no `@dataclass`).

## Identity: `DomainId`

Every entity has an id. Domino's `DomainId` wraps a `UUID` (default) or a `str`:

```python
from domino import DomainId

DomainId.generate()  # a fresh UUID-backed id
DomainId("ORD-2024-001")  # a string-based id
DomainId.empty()  # the "not yet assigned" sentinel
```

How ids are generated is [configurable](configuration.md) in one place.

## Entities

An entity declares an `_id` field. Equality and hashing are based on that id, so
two entities with the same id are "the same one" regardless of their other fields:

```python
from dataclasses import field
from domino import DomainId, Entity


class Customer(Entity):
    _id: DomainId = field(default_factory=DomainId.generate)
    name: str = ""


i = DomainId.generate()
Customer(_id=i, name="Ada") == Customer(_id=i, name="Grace")  # True — same id
Customer() == Customer()  # False — different ids
```

!!! tip "Give fields defaults"
    Declare `_id` with `default_factory=DomainId.generate`, and give the other
    fields defaults too. A dataclass field without a default can't follow one that
    has a default, so defaulting everything keeps construction flexible. When you
    need required inputs, prefer a `create()` classmethod (see below).

## Aggregate roots

An [aggregate root](../ddd/building-blocks.md#aggregates-and-aggregate-roots) is an
entity that is the **consistency boundary** for a cluster of objects and the only
way to change them. `AggregateRoot` adds domain-event recording on top of `Entity`:

```python
from dataclasses import field
from datetime import UTC, datetime
from decimal import Decimal

from domino import AggregateRoot, DomainEvent, DomainId, DomainStateError


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    total: str


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    customer_id: DomainId = field(default_factory=DomainId.generate)
    lines: list[dict] = field(default_factory=list)
    status: str = "draft"
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_line(self, product: str, quantity: int, unit_price: Money) -> None:
        if self.status != "draft":
            raise DomainStateError("cannot modify a non-draft order")
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
        self._add_event(
            OrderConfirmed(order_id=self._id, total=str(self.total().amount))
        )
```

The important part is *where the rules live*. `add_line` and `confirm` guard the
order's invariants, and because callers can only reach the lines *through* the
`Order`, there is no way to add a line to a confirmed order from the outside. That
is the consistency boundary doing its job.

### Recording events

Inside a behaviour method, call `self._add_event(...)` to record what happened. The
aggregate holds those events until someone pulls them:

```python
order.has_pending_events()  # -> bool
events = order.pull_pending_events()  # -> list[DomainEvent], and clears the list
```

You typically pull and publish **after** the transaction commits — see
[Domain events](events.md). You don't declare a field for pending events; the base
manages them.

### `_touch()` and timestamps

`AggregateRoot` offers `self._touch()` to refresh an `updated_at` timestamp at the
end of a state change. It's optional — declare an `updated_at` field if you want
it. On an aggregate that doesn't declare one, `_touch()` does nothing: it never
creates the attribute on the fly, which would put it outside the dataclass and
therefore outside equality and any imperative mapping.

### Factory methods

When creating an aggregate has its own rules or should emit a "created" event, a
`create()` classmethod reads better than a bare constructor:

```python
class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    customer_id: DomainId = field(default_factory=DomainId.generate)
    # ...

    @classmethod
    def place(cls, customer_id: DomainId) -> "Order":
        order = cls(customer_id=customer_id)
        order._add_event(OrderPlaced(order_id=order.id, customer_id=customer_id))
        return order
```

## Keeping aggregates small

Reference other aggregates by **id**, not by object — `Order` holds a `customer_id:
DomainId`, not a `Customer`. This keeps each aggregate a small, loadable unit and
keeps transactions focused on one aggregate at a time. To make something happen in
*another* aggregate, emit a domain event and let a handler drive it.

---

Next: [Domain events →](events.md)
