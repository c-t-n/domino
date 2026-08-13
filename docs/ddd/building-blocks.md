# The tactical building blocks

Tactical DDD is a small vocabulary of object types, each with a clear job. This
page explains them **conceptually** — what each is, when to reach for it, and the
rule of thumb that keeps them honest. Every one has a matching Domino class; the
*Building with Domino* section shows the code.

## Value objects

A **value object** is defined entirely by its attributes, not by an identity. Two
`Money(10, "EUR")` are the *same* value, the way two `5`s are the same number.

- **Immutable.** Once created it never changes; to "modify" it you build a new one.
- **Compared by value.** Equality and hashing are based on the fields.
- **Self-validating.** It refuses to exist in an invalid state — a negative
  `Money`, a malformed `EmailAddress`.

Value objects are where a surprising amount of domain logic lives. `Money` that
knows how to add itself (and refuses to add euros to dollars) removes a whole
class of bugs. **Rule of thumb:** if you don't care *which* one it is, only *what*
it is, it's a value object. → [`ValueObject`](../guide/value-objects.md)

## Entities

An **entity** has an **identity** that persists through change. A `Customer` is the
same customer after they change their name, email, and address — because the
identity (the id), not the attributes, defines them.

- **Compared by identity.** Two entities are equal iff their ids are equal.
- **Mutable over a lifecycle.** Its attributes change; its identity does not.

**Rule of thumb:** if "is it the same one?" is a meaningful question, it's an
entity. → [`Entity`](../guide/entities-aggregates.md)

## Aggregates and aggregate roots

An **aggregate** is a cluster of entities and value objects that must stay
consistent together, treated as a single unit. One entity is the **aggregate
root** — the only member the outside world is allowed to touch.

This is the most important — and most misunderstood — pattern. Its point is the
**consistency boundary**: any rule that must always hold ("an order's total equals
the sum of its lines") is enforced *inside* the aggregate, by going through the
root. Because the root is the only entry point, there is no way to reach in and
break the invariant.

Guidelines that keep aggregates healthy:

- **Keep them small.** Prefer one root plus the few objects that truly must change
  together. Large aggregates cause contention and clumsy loads.
- **Reference other aggregates by id,** not by object. An `Order` holds a
  `customer_id`, not a `Customer`.
- **One transaction, one aggregate.** A single unit of work should modify one
  aggregate; coordinate across aggregates with domain events.

→ [`AggregateRoot`](../guide/entities-aggregates.md)

## Domain events

A **domain event** records **something meaningful that happened**, in the past
tense: `OrderConfirmed`, `PaymentFailed`. It is an immutable fact.

Events are how one part of the system reacts to another *without* being coupled to
it. When an order is confirmed, the warehouse should reserve stock and the customer
should get an email — but the `Order` shouldn't know about warehouses or email. It
just records `OrderConfirmed`; handlers elsewhere react. **Rule of thumb:** if the
business would say "*when X happens, then Y*", X is a domain event.
→ [`DomainEvent` and the event bus](../guide/events.md)

## Repositories

A **repository** gives you a collection-like way to load and store aggregates,
hiding the database entirely. The domain asks for "the order with this id" and gets
back an `Order` — it never sees SQL, an ORM, or a query.

One repository serves one aggregate type, deals in whole aggregates (not rows or
DTOs), and is keyed by identity. The domain depends only on the repository's
*interface*; the concrete implementation lives in the infrastructure layer.
→ [Repositories & unit of work](../guide/persistence.md)

## Unit of work

A **unit of work** defines a transactional boundary: a set of changes that must
succeed or fail together. On a clean exit it commits; on an error it rolls back. It
is what makes "one transaction, one aggregate" enforceable.
→ [Repositories & unit of work](../guide/persistence.md)

## Domain services

Occasionally a piece of domain logic doesn't belong to any single entity or value
object — typically because it spans several aggregates (a funds transfer touches
two accounts). That logic goes in a **domain service**: a stateless object named
after a domain concept, living in the domain layer. Reach for it *only* when the
logic genuinely has no natural home on an entity — otherwise you drift back toward
an anemic model. → [`DomainService`](../guide/use-cases.md#domain-services)

## Commands and use cases

The patterns above model the domain. To *drive* it from the outside — an HTTP
request, a CLI command, a message — you use an application layer:

- A **command** is an immutable DTO describing an intent: *place this order*.
- A **use case** (a.k.a. application service) handles one such intent end to end:
  validate input, load and drive the aggregate, manage the transaction, return a
  result. It contains **no business logic** — it orchestrates; the domain decides.

→ [Commands & use cases](../guide/use-cases.md)

---

Next: [Layering & bounded contexts →](layering.md)
