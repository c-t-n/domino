"""Two services over RabbitMQ: routed by the broker, traced end to end.

Run it with a broker listening (see below)::

    docker run -d --rm -p 5672:5672 --name rabbit rabbitmq:3-alpine
    uv run --extra rabbitmq --extra sqlalchemy python examples/order_rabbitmq.py

Unlike the Redis example, this one needs a real server: there is no faithful
in-memory RabbitMQ. Set ``AMQP_URL`` to point somewhere else.

What it shows: an order committed with its event staged in the outbox, a relay
publishing that event to a topic exchange, and *two* services bound to different
routing keys — the warehouse wants confirmations, the auditor wants everything.
The broker, not the producer, decides who gets what.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import field
from decimal import Decimal

from sqlalchemy import Column, MetaData, Numeric, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import composite, registry
from sqlalchemy.pool import StaticPool

from domino import (
    AggregateRoot,
    AsyncEventBus,
    AsyncEventHandler,
    AsyncUseCase,
    Command,
    DomainEvent,
    DomainId,
    DomainStateError,
    EventRegistry,
    ValueObject,
    configure,
)
from domino.integrations.rabbitmq import (
    AsyncRabbitMQConsumer,
    AsyncRabbitMQPublisher,
    declare_event_exchange,
    declare_event_queue,
)
from domino.integrations.sqlalchemy import (
    AsyncOutboxRelay,
    AsyncSqlAlchemyRepository,
    AsyncSqlAlchemyUnitOfWork,
    DomainIdType,
    Outbox,
)

AMQP_URL = os.environ.get("AMQP_URL", "amqp://guest:guest@localhost:5672/")
EXCHANGE = "domino.example"

# --- The contract both services share ---------------------------------------


class Money(ValueObject):
    amount: Decimal
    currency: str


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    total: Money


class OrderCancelled(DomainEvent):
    order_id: DomainId
    reason: str


event_registry = EventRegistry()
event_registry.register_all([OrderConfirmed, OrderCancelled])


# --- Producer: the ordering service -----------------------------------------


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    status: str = "draft"
    total: Money = field(default_factory=lambda: Money(Decimal("0"), "EUR"))

    def confirm(self) -> None:
        if self.status != "draft":
            raise DomainStateError("only a draft order can be confirmed")
        self.status = "confirmed"
        self._add_event(OrderConfirmed(order_id=self._id, total=self.total))

    def cancel(self, reason: str) -> None:
        self.status = "cancelled"
        self._add_event(OrderCancelled(order_id=self._id, reason=reason))


metadata = MetaData()
mapper_registry = registry()

orders_table = Table(
    "orders",
    metadata,
    Column("id", DomainIdType, primary_key=True),
    Column("status", String(20), nullable=False),
    Column("total_amount", Numeric(12, 2), nullable=False),
    Column("total_currency", String(3), nullable=False),
)
mapper_registry.map_imperatively(
    Order,
    orders_table,
    properties={
        "_id": orders_table.c.id,
        "total": composite(
            Money, orders_table.c.total_amount, orders_table.c.total_currency
        ),
    },
)

outbox = Outbox(event_registry, metadata=metadata)


class OrderRepository(AsyncSqlAlchemyRepository[Order]):
    pass


class ConfirmOrderCommand(Command):
    order_id: DomainId


class ConfirmOrder(AsyncUseCase[ConfirmOrderCommand, None]):
    async def execute(self, command: ConfirmOrderCommand) -> None:
        order = await self._uow.orders.get_by_id(command.order_id)
        if order is None:
            raise DomainStateError(f"order {command.order_id} not found")
        order.confirm()
        await self._uow.orders.save(order)
        self._uow.enqueue_events(*order.pull_pending_events())


class CancelOrderCommand(Command):
    order_id: DomainId
    reason: str


class CancelOrder(AsyncUseCase[CancelOrderCommand, None]):
    async def execute(self, command: CancelOrderCommand) -> None:
        order = await self._uow.orders.get_by_id(command.order_id)
        if order is None:
            raise DomainStateError(f"order {command.order_id} not found")
        order.cancel(command.reason)
        await self._uow.orders.save(order)
        self._uow.enqueue_events(*order.pull_pending_events())


# --- Consumers: two services with different appetites -----------------------


class ReserveStock(AsyncEventHandler):
    async def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            self.log.info("reserving stock for order %s", event.order_id)


class WriteAuditLine(AsyncEventHandler):
    async def handle(self, event: DomainEvent) -> None:
        self.log.info("audit: %s", event.event_name)


# --- Demo -------------------------------------------------------------------


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-5s %(message)s", stream=sys.stdout
    )
    # aio-pika narrates every declaration at INFO; keep the demo readable.
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)
    configure(correlation_id_factory=lambda: "trace-42")

    try:
        import aio_pika

        connection = await aio_pika.connect_robust(AMQP_URL, timeout=3)
    except Exception as error:
        print(f"No RabbitMQ at {AMQP_URL} ({type(error).__name__}).")
        print("Start one with:")
        print("  docker run -d --rm -p 5672:5672 --name rabbit rabbitmq:3-alpine")
        return

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    uow = AsyncSqlAlchemyUnitOfWork(
        session_factory, {"orders": OrderRepository}, outbox=outbox
    )

    async with connection:
        channel = await connection.channel()
        exchange = await declare_event_exchange(channel, EXCHANGE)

        # The warehouse only cares about confirmations…
        warehouse_queue = await declare_event_queue(
            channel,
            "example.warehouse",
            exchange=exchange,
            routing_keys=["OrderConfirmed"],
        )
        # …the auditor takes everything on the exchange.
        audit_queue = await declare_event_queue(
            channel, "example.audit", exchange=exchange, routing_keys=["#"]
        )
        await warehouse_queue.purge()
        await audit_queue.purge()

        relay = AsyncOutboxRelay(
            session_factory,
            outbox,
            publisher=AsyncRabbitMQPublisher(exchange, event_registry),
        )

        warehouse_bus = AsyncEventBus()
        warehouse_bus.register(OrderConfirmed, ReserveStock())
        warehouse = AsyncRabbitMQConsumer(
            warehouse_queue, event_registry, bus=warehouse_bus
        )

        audit_bus = AsyncEventBus()
        audit_bus.register(OrderConfirmed, WriteAuditLine())
        audit_bus.register(OrderCancelled, WriteAuditLine())
        auditor = AsyncRabbitMQConsumer(audit_queue, event_registry, bus=audit_bus)

        print("--- the ordering service confirms one order and cancels another ---")
        confirmed = Order(total=Money(Decimal("220.00"), "EUR"))
        cancelled = Order(total=Money(Decimal("35.00"), "EUR"))
        async with uow:
            await uow.orders.save(confirmed)
            await uow.orders.save(cancelled)
        async with uow:
            await ConfirmOrder(uow).execute(ConfirmOrderCommand(order_id=confirmed.id))
        async with uow:
            await CancelOrder(uow).execute(
                CancelOrderCommand(order_id=cancelled.id, reason="out of stock")
            )
        print("  committed; both events staged in the outbox")

        print("--- the relay publishes them to the exchange ---")
        print(f"  {await relay.run_once()} events published")

        print("--- the warehouse gets only what it bound to ---")
        print(f"  {await warehouse.run_once()} event handled")

        print("--- the auditor gets everything ---")
        print(f"  {await auditor.run_once()} events handled")

        await warehouse_queue.delete()
        await audit_queue.delete()
        await channel.exchange_delete(EXCHANGE)
        for name in ("example.warehouse", "example.audit"):
            await (await channel.get_queue(f"{name}.dead")).delete()
            await channel.exchange_delete(f"{name}.dlx")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
