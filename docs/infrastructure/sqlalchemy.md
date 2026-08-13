# SQLAlchemy

Domino's core has no dependencies. The optional `domino.sqlalchemy` subpackage
implements the infrastructure layer — repositories and a unit of work — against
[SQLAlchemy](https://www.sqlalchemy.org/) 2.0.

```bash
uv add "domino[sqlalchemy]"
# or: pip install "domino[sqlalchemy]"
```

## Persistence-ignorant by design

The integration uses SQLAlchemy's **imperative mapping**: your domain classes stay
exactly as they are — plain Domino aggregates, entities and value objects with
**zero SQLAlchemy imports** — and you map them to tables separately. The payoff is
that the mapped class *is* your aggregate, so a repository returns real `Order`
objects, not separate "ORM models" you translate back and forth.

!!! note "Why not declarative mapping?"
    Making an aggregate inherit `DeclarativeBase` fails outright — a metaclass
    conflict between SQLAlchemy and Domino's `@dataclass_transform` bases — and
    even the workaround (a parallel "row" model plus hand-written translation)
    means maintaining two models and translating on every load and save.
    Imperative mapping keeps one model: your domain.

## Mapping an aggregate

Define tables, then map the domain classes to them. Value objects map across
columns with `composite()`; aggregate-internal entities map with `relationship()`.

```python
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Numeric, String, Table
from sqlalchemy.orm import composite, registry, relationship

from domino.sqlalchemy import DomainIdType

metadata = MetaData()
mapper_registry = registry()

orders_table = Table(
    "orders",
    metadata,
    Column("id", DomainIdType, primary_key=True),
    Column("customer_id", DomainIdType, nullable=False),
    Column("status", String(20), nullable=False),
)
order_lines_table = Table(
    "order_lines",
    metadata,
    Column("id", DomainIdType, primary_key=True),
    Column("order_id", DomainIdType, ForeignKey("orders.id"), nullable=False),
    Column("product", String(100), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("unit_price_amount", Numeric(12, 2), nullable=False),
    Column("unit_price_currency", String(3), nullable=False),
)

mapper_registry.map_imperatively(
    OrderLine,
    order_lines_table,
    properties={
        "_id": order_lines_table.c.id,
        "unit_price": composite(  # value object across two columns
            Money,
            order_lines_table.c.unit_price_amount,
            order_lines_table.c.unit_price_currency,
        ),
    },
)
mapper_registry.map_imperatively(
    Order,
    orders_table,
    properties={
        "_id": orders_table.c.id,
        "lines": relationship(OrderLine, cascade="all, delete-orphan"),  # children
    },
)
```

Two details worth noting:

- The primary-key attribute is Domino's `_id`, so map it explicitly:
  `"_id": table.c.id`. The rest of the columns map to same-named attributes
  automatically.
- Domino value objects are frozen dataclasses, which `composite()` supports
  natively — no extra glue.

### `DomainIdType`

A `TypeDecorator` that stores a `DomainId` as text and rebuilds it on load.
UUID-backed ids round-trip as UUIDs, string-backed ids as strings. Pass a length
for long string ids: `Column("id", DomainIdType(64))`.

## Repository

Subclass `SqlAlchemyRepository[T]` per aggregate. The aggregate type comes from
the generic parameter — nothing else to declare — and `get_by_id` / `save` /
`delete` are implemented for you. Add domain-specific finders using the session
exposed as `self._session`:

```python
from sqlalchemy import select
from domino.sqlalchemy import SqlAlchemyRepository


class OrderRepository(SqlAlchemyRepository[Order]):
    def by_customer(self, customer_id: DomainId) -> list[Order]:
        query = select(Order).where(orders_table.c.customer_id == customer_id)
        return list(self._session.scalars(query))
```

!!! tip "Reference the Table column in queries"
    In finders, filter on the **Table** column (`orders_table.c.customer_id`)
    rather than the ORM attribute (`Order.customer_id`). Imperative mapping doesn't
    surface typed columns on the class, so the Table reference is both correct and
    type-checker-friendly.

### Filtering with specifications

Instead of hand-writing a finder per query, mix in `Filterable[T]` to get
`list(*specifications)`. A [specification](../guide/specifications.md) is a
composable, persistence-ignorant criterion built from the field helpers (`eq`,
`ne`, `lt`, `le`, `gt`, `ge`, `in_`, `like`) and combined with `&` / `|` / `~`.

```python
from domino import eq, gt, in_
from domino.sqlalchemy import Filterable, SqlAlchemyRepository


class OrderRepository(SqlAlchemyRepository[Order], Filterable[Order]): ...


repo.list(eq("status", "confirmed"), in_("customer_id", [c1, c2]))  # AND-ed
repo.list(gt("priority", 5) | eq("status", "urgent"))  # OR
repo.list(~eq("status", "cancelled"))  # NOT
repo.list()  # everything
```

`Filterable` translates the specification into a SQL `WHERE` clause, filtering on
the aggregate's mapped fields. The same specification also evaluates **in memory**
(`spec.is_satisfied_by(order)`), so one criterion can drive both a query and a
domain check — see [Specifications](../guide/specifications.md).

## Unit of work

`SqlAlchemyUnitOfWork` opens **one session per scope**. Give it a session factory
and a mapping of name to repository *class*; entering the `with` block builds the
repositories on a fresh session and drives commit/rollback, and leaving it closes
the session.

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from domino.sqlalchemy import SqlAlchemyUnitOfWork

engine = create_engine("postgresql+psycopg://…")
session_factory = sessionmaker(engine, expire_on_commit=False)

uow = SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository})

with uow:
    order = uow.orders.get_by_id(order_id)
    order.confirm()
    uow.orders.save(order)
    # commit on clean exit, rollback on exception, session always closed
```

This is the same `UnitOfWork` your use cases already expect, so a
[use case](../guide/use-cases.md) doesn't change — only how you construct the
unit of work does.

!!! warning "Use `expire_on_commit=False`"
    By default SQLAlchemy expires an instance's attributes on commit, so touching
    an aggregate *after* its unit of work closes raises `DetachedInstanceError`.
    Building the session factory with `expire_on_commit=False` keeps aggregates
    usable after the transaction — the right default for this pattern.

`save` is `session.add`, which is correct for a new or a modified aggregate as
long as it was loaded within the same session (the unit-of-work norm). For a
detached aggregate from a previous session, use `uow.session.merge(aggregate)`.

## A full runnable example

See `examples/order_sqlalchemy.py` in the repository — the order domain, mapped
and persisted to SQLite end to end.
