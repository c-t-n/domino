# Specifications

A **specification** is a composable, reusable predicate over domain objects — a
named piece of business criteria you can evaluate, combine, and (with the
SQLAlchemy integration) turn into a database query. It keeps rules like "an active
premium customer" in one place instead of scattered `if` statements.

## Building a criterion

Use the field helpers, each naming an attribute, a comparison and a value:

```python
from domino import eq, ne, lt, le, gt, ge, in_, like

eq("status", "active")  # status == "active"
ne("status", "archived")  # status != "archived"
gt("age", 18)  # age > 18   (also lt, le, ge)
in_("tier", ["gold", "plat"])  # tier in (...)
like("name", "AC-%")  # SQL LIKE: % = any run, _ = one char
```

Evaluate one in memory with `is_satisfied_by`:

```python
eq("status", "active").is_satisfied_by(customer)  # -> bool
```

Criteria filter on **attribute names**, so the named field must exist on the
object (and, when translated to SQL, be a mapped column).

## Composing

Combine specifications with `&` (and), `|` (or) and `~` (not):

```python
active_adult = eq("status", "active") & ge("age", 18)
priority = gt("priority", 5) | eq("flagged", True)
not_cancelled = ~eq("status", "cancelled")

active_adult.is_satisfied_by(user)  # -> bool
```

The result is itself a `Specification`, so you can name and reuse business rules,
and build larger ones out of smaller ones.

## The payoff: one rule, two uses

The same specification runs **in memory** and, via the SQLAlchemy
[`Filterable`](../infrastructure/sqlalchemy.md#filtering-with-specifications)
mixin, **as SQL** — so a rule you query the database with is the same object you
can assert against a single aggregate in a domain test:

```python
big_confirmed = eq("status", "confirmed") & gt("total", 1000)

# as a query (Filterable adds list())
repo.list(big_confirmed)

# and in memory — same object, same logic
big_confirmed.is_satisfied_by(order)
```

## Custom specifications

For logic the field helpers can't express, subclass `Specification` and implement
`is_satisfied_by`. Hand-written specifications work in memory and compose with the
others; they aren't translated to SQL, so evaluate them on already-loaded
aggregates.

```python
from domino import Specification


class HasOverdueLines(Specification):
    def is_satisfied_by(self, order) -> bool:
        return any(line.is_overdue() for line in order.lines)


rule = eq("status", "confirmed") & HasOverdueLines()
[o for o in orders if rule.is_satisfied_by(o)]
```
