# Why Domain-Driven Design?

Domain-Driven Design (DDD) is an approach to building software where the **domain
— the business problem you are solving — is the heart of the design**. Instead of
letting a database schema or a web framework dictate the shape of your code, you
model the concepts, rules and language of the business directly, and keep that
model isolated from technical concerns.

## The problem it solves

Most non-trivial applications accumulate business rules: an order can only be
shipped once it is paid, a discount can't push a price below zero, an account
can't be overdrawn. When these rules are scattered across controllers, SQL
queries, and UI callbacks, a few things go wrong:

- **The rules drift.** The same rule is enforced in three places and one of them
  is subtly wrong.
- **The model is anemic.** Objects are bags of getters and setters, and the logic
  that gives them meaning lives elsewhere. Nothing stops you from putting an
  object into an invalid state.
- **The code and the conversation diverge.** The business says "confirm an order";
  the code says `UPDATE orders SET status = 2`. Every change requires a
  translation step, and translations leak bugs.

DDD's answer is to put the rules **inside the model**, express them in the
**language the business uses**, and protect the model from infrastructure.

## The ubiquitous language

The single most important idea in DDD is the **ubiquitous language**: developers
and domain experts agree on one vocabulary, and that vocabulary appears verbatim
in the code. If the business says *place order*, *confirm*, *ship*, *cancel*,
then those are your method names — not `create`, `update`, `process`.

A shared language means a conversation with a domain expert maps directly onto the
code, and a code review can be read aloud to a domain expert. This is not
cosmetic: naming is how you discover the model.

## Strategic vs. tactical DDD

DDD comes in two halves:

- **Strategic DDD** is about the big picture: carving a large system into
  **bounded contexts** (areas where a term has one precise meaning), and defining
  how those contexts relate. "Customer" in *Sales* is not the same as "Customer"
  in *Support*, and pretending otherwise creates a tangled model. See
  [Layering & bounded contexts](layering.md).
- **Tactical DDD** is the toolbox for modelling *inside* one bounded context:
  value objects, entities, aggregates, domain events, repositories, and so on. See
  [The building blocks](building-blocks.md).

**Domino is a tactical DDD library.** It gives you the building blocks for one
bounded context and stays out of your strategic decisions.

## When is DDD worth it?

DDD earns its keep when the **domain is complex** — when the value of the software
is in the rules, not the plumbing. An order-management system, an insurance
quoting engine, a payroll calculator: these reward a rich model.

It is overkill for simple CRUD. If your app mostly moves rows between a form and a
table with little logic in between, a thin service layer is cheaper and clearer.
DDD is a tool for taming **complexity**, and applying it where there is none just
adds ceremony.

A good heuristic: if you find yourself explaining a rule to a colleague and it
takes more than a sentence, that rule wants to live in a well-named place in your
domain model. That is where Domino helps.

---

Next: [The tactical building blocks →](building-blocks.md)
