"""Exposing a Domino domain over HTTP with FastAPI (presentation layer).

Serve it with an ASGI server::

    uv run --extra fastapi --extra sqlalchemy \\
        uvicorn examples.order_fastapi:app --reload

…or just run this file for an in-process demo (needs httpx, bundled with the dev
setup)::

    uv run python examples/order_fastapi.py

The domain and its imperative mapping are the *same* pristine Domino aggregates
as the other examples. The presentation layer only translates HTTP ↔ commands and
maps domain errors to status codes; the use case still owns the transaction, and
the unit of work publishes domain events after commit.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import field
from decimal import Decimal
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Numeric, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import composite, registry, relationship
from sqlalchemy.pool import StaticPool

from domino import (
    AggregateRoot,
    AsyncUseCase,
    Command,
    DomainEvent,
    DomainId,
    DomainNotFoundError,
    DomainStateError,
    Entity,
    ValueObject,
    configure,
)
from domino.events import EventBus, EventHandler
from domino.fastapi import UnitOfWorkDep, install_domino, query_filter
from domino.sqlalchemy import (
    AsyncFilterable,
    AsyncSqlAlchemyRepository,
    AsyncSqlAlchemyUnitOfWork,
    DomainIdType,
)

# --- Domain (pure Domino, zero framework) ----------------------------------


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


class OrderConfirmed(DomainEvent):
    order_id: DomainId


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
        if self.status == "confirmed":
            raise DomainStateError("order is already confirmed")
        if not self.lines:
            raise DomainStateError("cannot confirm an empty order")
        self.status = "confirmed"
        self._add_event(OrderConfirmed(order_id=self._id))


# --- Infrastructure: tables + imperative mapping ----------------------------

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
    pass


# --- Application: commands + use cases --------------------------------------


class PlaceOrderCommand(Command):
    customer_id: DomainId
    product: str
    quantity: int
    unit_price: Decimal


class PlaceOrder(AsyncUseCase[PlaceOrderCommand, DomainId]):
    def __init__(self, uow: AsyncSqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: PlaceOrderCommand) -> DomainId:
        async with self._uow:
            order = Order(customer_id=command.customer_id)
            order.add_line(
                command.product, command.quantity, Money(command.unit_price, "EUR")
            )
            await self._uow.orders.save(order)
        return order.id


class ConfirmOrderCommand(Command):
    order_id: DomainId


class ConfirmOrder(AsyncUseCase[ConfirmOrderCommand, None]):
    def __init__(self, uow: AsyncSqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: ConfirmOrderCommand) -> None:
        async with self._uow:
            order = await self._uow.orders.get_by_id(command.order_id)
            if order is None:
                raise DomainNotFoundError(f"order {command.order_id} not found")
            order.confirm()
            await self._uow.orders.save(order)


# --- Event handling ---------------------------------------------------------


class AnnounceConfirmation(EventHandler):
    def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            self.log.info(
                "order %s confirmed [cid=%s]", event.order_id, event.correlation_id
            )


# --- Presentation: the FastAPI app ------------------------------------------

# Domino's global config is loaded once, at startup (here: 16-char ids).
configure(correlation_id_factory=lambda: uuid4().hex[:16])

engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
session_factory = async_sessionmaker(engine, expire_on_commit=False)

event_bus = EventBus()
event_bus.register(OrderConfirmed, AnnounceConfirmation())


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Orders", lifespan=lifespan)
# Middleware and handlers are installed here, at construction (before startup);
# the per-request state reads the session factory and event bus.
install_domino(
    app,
    session_factory=session_factory,
    repositories={"orders": OrderRepository},
    event_bus=event_bus,
)


class PlaceOrderBody(BaseModel):
    customer_id: str
    product: str
    quantity: int
    unit_price: Decimal


OrderFilters = Annotated[list, Depends(query_filter({"status": str}))]


@app.post("/orders", status_code=201)
async def place_order(body: PlaceOrderBody, uow: UnitOfWorkDep) -> dict[str, str]:
    order_id = await PlaceOrder(uow).execute(
        PlaceOrderCommand(
            customer_id=DomainId(body.customer_id),
            product=body.product,
            quantity=body.quantity,
            unit_price=body.unit_price,
        )
    )
    return {"id": str(order_id)}


@app.get("/orders/{order_id}")
async def get_order(order_id: str, uow: UnitOfWorkDep) -> dict[str, object]:
    async with uow:
        order = await uow.orders.get_by_id(DomainId(order_id))
        if order is None:
            raise DomainNotFoundError(f"order {order_id} not found")
        return {
            "id": str(order.id),
            "status": order.status,
            "total": str(order.total().amount),
        }


@app.post("/orders/{order_id}/confirm", status_code=204)
async def confirm_order(order_id: str, uow: UnitOfWorkDep) -> None:
    await ConfirmOrder(uow).execute(ConfirmOrderCommand(order_id=DomainId(order_id)))


@app.get("/orders")
async def list_orders(uow: UnitOfWorkDep, specs: OrderFilters) -> list[dict[str, str]]:
    async with uow:
        orders = await uow.orders.list(*specs)
        return [{"id": str(o.id), "status": o.status} for o in orders]


# --- In-process demo (run this file directly) -------------------------------


def _demo() -> None:
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        print("Install httpx (or fastapi[standard]) to run the in-process demo,")
        print("or serve it: uvicorn examples.order_fastapi:app --reload")
        return

    customer = str(DomainId.generate())
    with TestClient(app) as client:
        print("--- placing an order ---")
        created = client.post(
            "/orders",
            json={
                "customer_id": customer,
                "product": "Mechanical keyboard",
                "quantity": 1,
                "unit_price": "150.00",
            },
            headers={"X-Request-ID": "demo-trace-1"},
        )
        order_id = created.json()["id"]
        cid = created.headers["X-Request-ID"]
        print(f"  {created.status_code} id={order_id} cid={cid}")

        print("--- confirming (publishes OrderConfirmed) ---")
        confirmed = client.post(f"/orders/{order_id}/confirm")
        print(f"  {confirmed.status_code}")

        print("--- confirming again → 409 STATE_ERROR ---")
        again = client.post(f"/orders/{order_id}/confirm")
        print(f"  {again.status_code} {again.json()}")

        print("--- filtering confirmed orders ---")
        listed = client.get("/orders", params={"status": "confirmed"})
        print(f"  {listed.status_code} {listed.json()}")

        print("--- unknown order → 404 NOT_FOUND ---")
        missing = client.get(f"/orders/{DomainId.generate()}")
        print(f"  {missing.status_code} {missing.json()['code']}")


if __name__ == "__main__":
    _demo()
