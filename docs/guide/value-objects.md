# Value objects

A [value object](../ddd/building-blocks.md#value-objects) is immutable and compared
by value. Subclass `ValueObject` and declare fields — it becomes a **frozen
dataclass**, so you get value equality, hashing and immutability for free.

```python
from decimal import Decimal
from domino import ValueObject, DomainValidationError


class Money(ValueObject):
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise DomainValidationError("amount cannot be negative")
        if len(self.currency) != 3:
            raise DomainValidationError(f"invalid currency: {self.currency}")
```

```python
Money(Decimal("10"), "EUR") == Money(Decimal("10"), "EUR")  # True
Money(Decimal("10"), "EUR") == Money(Decimal("20"), "EUR")  # False
hash(Money(Decimal("10"), "EUR"))  # hashable → dict/set keys
```

!!! warning "No `@dataclass`"
    Don't decorate the class yourself — `ValueObject` already applies
    `@dataclass(frozen=True)`. Adding your own decorator applies it twice.

## Validation

Put invariants in `__post_init__`. A value object that constructs successfully is,
by definition, valid — nowhere else in the code needs to re-check. Raise
[`DomainValidationError`](use-cases.md) (or a subclass) so the application layer can
translate it into an HTTP 400 or a user message.

## Immutability and `replace`

Value objects are frozen, so you never mutate one — you build a new one. The base
provides `replace()` (a thin wrapper over `dataclasses.replace`) for the common
"same but with one field changed" case:

```python
price = Money(Decimal("10"), "EUR")
discounted = price.replace(amount=Decimal("8"))  # a new Money; `price` is unchanged
```

Trying to assign a field raises:

```python
price.amount = Decimal("5")  # FrozenInstanceError
```

## Behaviour belongs here too

Value objects are not just data — they are a natural home for domain logic. `Money`
that knows how to add itself, and refuses to mix currencies, removes an entire
class of bugs from the rest of the codebase:

```python
class Money(ValueObject):
    amount: Decimal
    currency: str

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise DomainValidationError("cannot add different currencies")
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, factor: int) -> "Money":
        return Money(self.amount * factor, self.currency)
```

```python
Money(Decimal("10"), "EUR") + Money(Decimal("5"), "EUR")  # Money(15, EUR)
Money(Decimal("10"), "EUR") + Money(Decimal("5"), "USD")  # DomainValidationError
```

## Equality across types

Two different value-object classes are never equal, even with identical fields — a
`Money(10, "EUR")` is not a `Weight(10, "EUR")`. That falls out of the dataclass
equality Domino applies, so you don't have to think about it.

---

Next: [Entities & aggregates →](entities-aggregates.md)
