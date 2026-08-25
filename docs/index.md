# Domino

A small, dependency-free library for building **Domain-Driven Design** domains in
Python 3.12+. Domino gives you clean base classes for the tactical DDD patterns
and applies the right `@dataclass` for you, so your domain reads as plain classes
with fields — no framework ceremony.

```python
from decimal import Decimal
from domino import ValueObject, DomainValidationError


class Money(ValueObject):
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise DomainValidationError("amount cannot be negative")


Money(Decimal("10"), "EUR") == Money(Decimal("10"), "EUR")  # True — compared by value
```

## Who this documentation is for

These docs do two things at once, so pick the entry point that fits you:

- **New to Domain-Driven Design?** Start with [Why DDD?](ddd/why.md). The
  *Domain-Driven Design* section teaches the ideas — the ubiquitous language, the
  tactical building blocks, and how to layer an application — independently of any
  library.
- **Know DDD, want to build?** Jump to the [Quickstart](guide/quickstart.md) and
  the *Building with Domino* section, which maps each pattern to a Domino class
  with runnable examples.
- **Want to see it all wired together?** Read the
  [Order domain tutorial](tutorial/order-domain.md).

## What Domino gives you

| Pattern | Class |
| --- | --- |
| Value object | `ValueObject` |
| Entity | `Entity` |
| Aggregate root | `AggregateRoot` |
| Domain event | `DomainEvent` |
| Event bus / handler | `EventBus` / `EventHandler` |
| Repository | `Repository[T]` / `AsyncRepository[T]` |
| Unit of work | `UnitOfWork` / `AsyncUnitOfWork` |
| Command / use case | `Command` / `UseCase[C, R]` (or `AsyncUseCase[C, R]`) |
| Domain service | `DomainService` |

On top of the building blocks, Domino adds three cross-cutting features that need
**zero plumbing**: [correlation ids](guide/observability.md) that propagate
automatically, [contextual logging](guide/observability.md) via `self.log`, and a
single [`configure()`](guide/configuration.md) hook.

!!! note "Scope"
    Domino implements the **domain-events** pattern — an aggregate records events
    for you to publish. It is **not** an event-sourcing framework: there is no
    event store and aggregates are not rebuilt from a stream.

## Install

```bash
uv add pydomino
# or: pip install pydomino
```

The distribution is named `pydomino` (`domino` was already taken on PyPI); what
you import stays `domino`.

Requires Python 3.12+ and has no runtime dependencies.
