# Layering & bounded contexts

Tactical patterns give you good objects. **Layering** decides where those objects
live and, crucially, which of them is allowed to know about which. Getting the
dependency direction right is what keeps a domain model pure and testable.

## The layers

A DDD application is usually split into three layers:

```
┌─────────────────────────────────────────────────────────┐
│  Application    use cases, commands                      │  orchestrates
│                 (one entry point per user goal)          │
├─────────────────────────────────────────────────────────┤
│  Domain         value objects, entities, aggregates,     │  the model
│                 domain events, domain services           │  (pure)
├─────────────────────────────────────────────────────────┤
│  Infrastructure repositories, event bus wiring,          │  implements
│                 database sessions, message brokers        │  the ports
└─────────────────────────────────────────────────────────┘
```

- **Domain** holds the model and its rules. It is the most valuable and the most
  protected layer.
- **Application** holds use cases that orchestrate the domain to fulfil a request.
  Thin: no business rules.
- **Infrastructure** implements the technical details — the actual database, the
  actual message bus.

## The dependency rule

The one rule that makes layering work: **dependencies point inward.**

- The **domain layer depends on nothing** — not on the database, not on the web
  framework, not even on the application layer. It is plain objects and rules. This
  is what makes it trivially unit-testable and long-lived.
- The **application layer depends on the domain**, and on repository *interfaces*
  (ports) — never on concrete stores.
- The **infrastructure layer depends on both**, implementing the ports the inner
  layers declared.

This is the *dependency inversion* at the heart of DDD: the domain defines a
`Repository` interface it needs; the infrastructure provides a SQL implementation.
The arrow of dependency is inverted relative to the flow of control.

!!! tip "How Domino maps to the layers"
    - **Domain:** `ValueObject`, `Entity`, `AggregateRoot`, `DomainEvent`,
      `DomainService`, and your `Repository[T]` *interface*.
    - **Application:** `Command`, `UseCase[C, R]`, and `UnitOfWork`.
    - **Infrastructure:** your concrete `Repository` implementations and your
      `EventBus`/handler wiring.

    A concrete package layout — one Domino [scaffolds for
    you](../reference/scaffolding.md) — looks like:

    ```
    billing/
    ├── domain/          value_objects.py  aggregates.py  events.py
    ├── application/     commands.py  use_cases.py
    └── infrastructure/  repositories.py
    ```

## Bounded contexts

Everything above describes **one** model. Real systems have several. A **bounded
context** is the boundary within which a model — and its ubiquitous language — is
consistent and unambiguous.

The classic example: the word *Customer*. In a **Sales** context a customer has a
credit limit and a pipeline stage; in **Support** a customer has open tickets and a
satisfaction score; in **Shipping** a customer is really just an address. Forcing
one `Customer` class to serve all three produces a bloated model where no term
means one thing. Instead you have three `Customer` types, one per context, each
precise — and you translate between contexts explicitly at their edges.

Deciding where those boundaries fall is **strategic DDD**, and it is largely a
modelling and organisational exercise rather than a coding one. Domino doesn't
impose a context structure; it gives you clean building blocks so that **each
bounded context** you identify can be modelled cleanly on its own terms. A common
approach is one Python package per bounded context, each with the three layers
above.

---

Ready to build? [Quickstart →](../guide/quickstart.md)
