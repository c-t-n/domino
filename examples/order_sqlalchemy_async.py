"""Persisting a Domino domain with async SQLAlchemy (imperative mapping).

Run it with::

    uv run --extra sqlalchemy python examples/order_sqlalchemy_async.py

The domain classes are the *same* pristine Domino aggregates as the synchronous
example — only the infrastructure changes: an ``AsyncEngine``, async repositories
and an async unit of work driven with ``async with`` / ``await``.

Needs an async driver; this uses ``aiosqlite`` (``pip install aiosqlite``).
"""

from __future__ import annotations

import asyncio
from dataclasses import field
from decimal import Decimal

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    select,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import composite, registry, relationship

from domino import AggregateRoot, DomainId, DomainStateError, Entity, ValueObject, eq
from domino.integrations.sqlalchemy import (
    AsyncFilterable,
    AsyncSqlAlchemyRepository,
    AsyncSqlAlchemyUnitOfWork,
    DomainIdType,
)

# --- Domain (pure Domino, zero SQLAlchemy) ---------------------------------


class Money(ValueObject):
    amount: Decimal
    currency: str

    def __mul__(self, factor: int) -> Money:
        return Money(self.amount * factor, self.currency)

    def __add__(self, other: Money) -> Money:
        return Money(self.amount + other.amount, self.currency)


class OrderLine(Entity):
    _id: DomainId = field(default_factory=DomainId.generate)
    product: str = ""
    quantity: int = 0
    unit_price: Money = field(default_factory=lambda: Money(Decimal("0"), "EUR"))

    def subtotal(self) -> Money:
        return self.unit_price * self.quantity


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    customer_id: DomainId = field(default_factory=DomainId.generate)
    lines: list[OrderLine] = field(default_factory=list)
    status: str = "draft"

    def add_line(self, product: str, quantity: int, unit_price: Money) -> None:
        if self.status != "draft":
            raise DomainStateError("cannot modify a non-draft order")
        self.lines.append(
            OrderLine(product=product, quantity=quantity, unit_price=unit_price)
        )

    def total(self) -> Money:
        return sum((line.subtotal() for line in self.lines), Money(Decimal("0"), "EUR"))

    def confirm(self) -> None:
        if not self.lines:
            raise DomainStateError("cannot confirm an empty order")
        self.status = "confirmed"


# --- Infrastructure: tables, imperative mapping, repository ----------------

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
        "unit_price": composite(
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
        "lines": relationship(OrderLine, cascade="all, delete-orphan"),
    },
)


class OrderRepository(AsyncSqlAlchemyRepository[Order], AsyncFilterable[Order]):
    async def by_customer(self, customer_id: DomainId) -> list[Order]:
        query = select(Order).where(orders_table.c.customer_id == customer_id)
        result = await self._session.scalars(query)
        return list(result)


# --- Wiring -----------------------------------------------------------------


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")  # in-memory
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    # expire_on_commit=False keeps aggregates usable after the transaction closes.
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    uow = AsyncSqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository})

    customer = DomainId.generate()

    print("--- placing an order ---")
    order = Order(customer_id=customer)
    order.add_line("Mechanical keyboard", 1, Money(Decimal("150.00"), "EUR"))
    order.add_line("USB-C hub", 2, Money(Decimal("35.00"), "EUR"))
    order_id = order.id
    async with uow:
        await uow.orders.save(order)
    print(f"  saved order {order_id} — total {order.total().amount} EUR")

    print("--- reloading and confirming ---")
    async with uow:
        reloaded = await uow.orders.get_by_id(order_id)
        assert reloaded is not None
        print(f"  loaded {len(reloaded.lines)} line(s), status {reloaded.status!r}")
        reloaded.confirm()
        await uow.orders.save(reloaded)

    print("--- querying by customer ---")
    async with uow:
        found = await uow.orders.by_customer(customer)
        print(f"  {len(found)} order(s) for the customer, first is {found[0].status!r}")

    print("--- filtering with specifications ---")
    async with uow:
        confirmed = await uow.orders.list(eq("status", "confirmed"))
        print(f"  {len(confirmed)} confirmed order(s)")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
