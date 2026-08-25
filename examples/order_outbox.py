"""Publishing domain events reliably, with a transactional outbox.

Run it with::

    uv run --extra sqlalchemy python examples/order_outbox.py

Publishing straight after a commit leaves a window: if the process dies between
the two, the event is gone and nothing records that it existed. The outbox
closes it — events are written to a table *inside* the transaction that produced
them, and a relay ships them afterwards.

The demo walks through what that buys you: a commit that stages an event without
publishing it, a rollback that takes the event with it, a broker outage that
loses nothing, and the housekeeping that follows.

Needs an async driver; this uses ``aiosqlite`` (``pip install aiosqlite``).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import field
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import Column, MetaData, Numeric, String, Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import composite, registry
from sqlalchemy.pool import StaticPool

from domino import (
    AggregateRoot,
    AsyncEventPublisher,
    Command,
    DomainEvent,
    DomainId,
    DomainStateError,
    EventRegistry,
    ValueObject,
)
from domino.application.use_case import AsyncUseCase
from domino.integrations.sqlalchemy import (
    AsyncOutboxRelay,
    AsyncSqlAlchemyRepository,
    AsyncSqlAlchemyUnitOfWork,
    DomainIdType,
    Outbox,
)

# --- Domain (pure Domino, zero SQLAlchemy) ----------------------------------


class Money(ValueObject):
    amount: Decimal
    currency: str


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    customer_id: DomainId
    total: Money


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    customer_id: DomainId = field(default_factory=DomainId.generate)
    status: str = "draft"
    total: Money = field(default_factory=lambda: Money(Decimal("0"), "EUR"))

    def confirm(self) -> None:
        if self.status != "draft":
            raise DomainStateError("only a draft order can be confirmed")
        self.status = "confirmed"
        self._add_event(
            OrderConfirmed(
                order_id=self._id, customer_id=self.customer_id, total=self.total
            )
        )


# --- Infrastructure: tables, mapping, outbox --------------------------------

metadata = MetaData()
mapper_registry = registry()

orders_table = Table(
    "orders",
    metadata,
    Column("id", DomainIdType, primary_key=True),
    Column("customer_id", DomainIdType, nullable=False),
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


class OrderRepository(AsyncSqlAlchemyRepository[Order]):
    pass


# Events must be registered to cross a process boundary: the relay decodes what
# it reads back from the table.
event_registry = EventRegistry()
event_registry.register(OrderConfirmed)

# The outbox declares its table on the same metadata, so create_all builds it.
outbox = Outbox(event_registry, metadata=metadata)


# --- The broker, faked ------------------------------------------------------


class PrintingBroker(AsyncEventPublisher):
    """Stands in for Kafka, RabbitMQ or Redis Streams."""

    def __init__(self) -> None:
        self.down = False
        self.delivered: list[DomainEvent] = []

    async def publish(self, *events: DomainEvent) -> None:
        if self.down:
            raise ConnectionError("broker unreachable")
        for event in events:
            self.delivered.append(event)
            print(f"  → published {event_registry.encode_json(event)}")


# --- Application ------------------------------------------------------------


class ConfirmOrderCommand(Command):
    order_id: DomainId


class ConfirmOrder(AsyncUseCase[ConfirmOrderCommand, None]):
    async def execute(self, command: ConfirmOrderCommand) -> None:
        order = await self._uow.orders.get_by_id(command.order_id)
        if order is None:
            raise DomainStateError(f"order {command.order_id} not found")
        order.confirm()
        await self._uow.orders.save(order)
        # Queued, not published: the unit of work writes these to the outbox
        # inside the transaction.
        self._uow.enqueue_events(*order.pull_pending_events())


# --- Demo -------------------------------------------------------------------


async def _pending_lines(session_factory) -> list:
    async with session_factory() as session:
        result = await session.execute(
            select(outbox.table).where(outbox.table.c.published_at.is_(None))
        )
        return result.all()


async def main() -> None:
    # Log to stdout, so the relay's error lands in step order with the prints.
    logging.basicConfig(
        level=logging.ERROR, format="%(levelname)-5s %(message)s", stream=sys.stdout
    )

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    broker = PrintingBroker()
    uow = AsyncSqlAlchemyUnitOfWork(
        session_factory, {"orders": OrderRepository}, outbox=outbox
    )
    relay = AsyncOutboxRelay(session_factory, outbox, publisher=broker)

    order = Order(total=Money(Decimal("220.00"), "EUR"))
    async with uow:
        await uow.orders.save(order)

    print("--- confirming an order ---")
    async with uow:
        await ConfirmOrder(uow).execute(ConfirmOrderCommand(order_id=order.id))
    print(f"  committed, {len(await _pending_lines(session_factory))} event staged")
    print(f"  delivered so far: {len(broker.delivered)} (the relay hasn't run yet)")

    print("--- the relay ships it ---")
    print(f"  {await relay.run_once()} event published")

    print("--- a transaction that rolls back leaves nothing behind ---")
    try:
        async with uow:
            doomed = Order(total=Money(Decimal("10.00"), "EUR"))
            doomed.confirm()
            await uow.orders.save(doomed)
            uow.enqueue_events(*doomed.pull_pending_events())
            raise RuntimeError("something went wrong downstream")
    except RuntimeError as error:
        print(f"  rolled back on: {error}")
    print(f"  events staged: {len(await _pending_lines(session_factory))}")

    print("--- the broker goes down: the event waits, it is never lost ---")
    broker.down = True
    second = Order(total=Money(Decimal("35.00"), "EUR"))
    async with uow:
        await uow.orders.save(second)
    async with uow:
        await ConfirmOrder(uow).execute(ConfirmOrderCommand(order_id=second.id))
    print(f"  {await relay.run_once()} published while down")
    (line,) = await _pending_lines(session_factory)
    print(f"  still queued: {line.event_name}, attempts={line.attempts}")

    print("--- the broker recovers: the relay resumes where it stopped ---")
    broker.down = False
    print(f"  {await relay.run_once()} event published")
    print(f"  pending: {len(await _pending_lines(session_factory))}")

    print("--- housekeeping: drop the lines already sent ---")
    recent = await relay.purge(older_than=timedelta(days=7))
    print(f"  removed with a 7-day window: {recent} (these are too recent to drop)")
    dropped = await relay.purge(older_than=timedelta(seconds=-1))
    print(f"  removed with no window at all: {dropped}")
    pending = len(await _pending_lines(session_factory))
    print(f"  unpublished lines are never purged: {pending} left")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
