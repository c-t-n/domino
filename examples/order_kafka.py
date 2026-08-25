"""Kafka: a log you can replay, keyed so one aggregate stays in order.

Run it with a broker listening (Redpanda starts in a couple of seconds)::

    docker run -d --rm -p 19092:19092 --name redpanda \\
      redpandadata/redpanda:latest redpanda start \\
      --overprovisioned --smp 1 --memory 512M --node-id 0 --check=false \\
      --kafka-addr external://0.0.0.0:19092 \\
      --advertise-kafka-addr external://localhost:19092

    uv run --extra kafka --extra sqlalchemy python examples/order_kafka.py

Set ``KAFKA_BOOTSTRAP_SERVERS`` to point elsewhere. Like RabbitMQ, this one needs
a real broker.

What it shows, beyond the other examples: events keyed on the aggregate id land
on one partition and stay in order, and a *second* service joining later replays
the whole history — a queue would have nothing left to give it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
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
from domino.integrations.kafka import (
    AsyncKafkaConsumer,
    AsyncKafkaPublisher,
    aggregate_key,
)
from domino.integrations.sqlalchemy import (
    AsyncOutboxRelay,
    AsyncSqlAlchemyRepository,
    AsyncSqlAlchemyUnitOfWork,
    DomainIdType,
    Outbox,
)

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
TOPIC = f"domino-orders-{uuid.uuid4().hex[:8]}"

# --- The contract both services share ---------------------------------------


class Money(ValueObject):
    amount: Decimal
    currency: str


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    total: Money


class OrderShipped(DomainEvent):
    order_id: DomainId


event_registry = EventRegistry()
event_registry.register_all([OrderConfirmed, OrderShipped])


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

    def ship(self) -> None:
        if self.status != "confirmed":
            raise DomainStateError("only a confirmed order can ship")
        self.status = "shipped"
        self._add_event(OrderShipped(order_id=self._id))


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


class AdvanceOrderCommand(Command):
    order_id: DomainId


class ConfirmOrder(AsyncUseCase[AdvanceOrderCommand, None]):
    async def execute(self, command: AdvanceOrderCommand) -> None:
        order = await self._uow.orders.get_by_id(command.order_id)
        if order is None:
            raise DomainStateError(f"order {command.order_id} not found")
        order.confirm()
        await self._uow.orders.save(order)
        self._uow.enqueue_events(*order.pull_pending_events())


class ShipOrder(AsyncUseCase[AdvanceOrderCommand, None]):
    async def execute(self, command: AdvanceOrderCommand) -> None:
        order = await self._uow.orders.get_by_id(command.order_id)
        if order is None:
            raise DomainStateError(f"order {command.order_id} not found")
        order.ship()
        await self._uow.orders.save(order)
        self._uow.enqueue_events(*order.pull_pending_events())


# --- Consumers ---------------------------------------------------------------


class ReserveStock(AsyncEventHandler):
    async def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            self.log.info("reserving stock for order %s", event.order_id)


class BuildReadModel(AsyncEventHandler):
    """A service that joins later and catches up from the beginning."""

    def __init__(self) -> None:
        self.timeline: list[str] = []

    async def handle(self, event: DomainEvent) -> None:
        self.timeline.append(event.event_name)


# --- Demo --------------------------------------------------------------------


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-5s %(message)s", stream=sys.stdout
    )
    for noisy in ("aiokafka", "kafka"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    configure(correlation_id_factory=lambda: "trace-42")

    try:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
        from aiokafka.admin import AIOKafkaAdminClient, NewTopic

        admin = AIOKafkaAdminClient(
            bootstrap_servers=BOOTSTRAP, request_timeout_ms=3000
        )
        await admin.start()
    except Exception as error:
        print(f"No Kafka at {BOOTSTRAP} ({type(error).__name__}).")
        print("Start Redpanda with the command in this file's docstring.")
        return

    # Several partitions, so keying on the aggregate id actually means something.
    await admin.create_topics([NewTopic(TOPIC, num_partitions=4, replication_factor=1)])
    await admin.close()

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    uow = AsyncSqlAlchemyUnitOfWork(
        session_factory, {"orders": OrderRepository}, outbox=outbox
    )

    producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP)
    await producer.start()
    try:
        relay = AsyncOutboxRelay(
            session_factory,
            outbox,
            publisher=AsyncKafkaPublisher(
                producer, event_registry, topic=TOPIC, key=aggregate_key("order_id")
            ),
        )

        print("--- the ordering service confirms, then ships, one order ---")
        order = Order(total=Money(Decimal("220.00"), "EUR"))
        async with uow:
            await uow.orders.save(order)
        async with uow:
            await ConfirmOrder(uow).execute(AdvanceOrderCommand(order_id=order.id))
        async with uow:
            await ShipOrder(uow).execute(AdvanceOrderCommand(order_id=order.id))
        print("  committed; both events staged in the outbox")

        print("--- the relay publishes them, keyed on the order id ---")
        print(f"  {await relay.run_once()} events published to {TOPIC}")

        print("--- the warehouse consumes them ---")
        warehouse_bus = AsyncEventBus()
        warehouse_bus.register(OrderConfirmed, ReserveStock())
        warehouse_raw = AIOKafkaConsumer(
            TOPIC,
            bootstrap_servers=BOOTSTRAP,
            group_id="warehouse",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await warehouse_raw.start()
        try:
            warehouse = AsyncKafkaConsumer(
                warehouse_raw, event_registry, bus=warehouse_bus
            )
            print(f"  {await warehouse.run_once(timeout_ms=5000)} events handled")
        finally:
            await warehouse_raw.stop()

        print("--- a reporting service joins later and replays the history ---")
        read_model = BuildReadModel()
        reporting_bus = AsyncEventBus()
        reporting_bus.register(OrderConfirmed, read_model)
        reporting_bus.register(OrderShipped, read_model)
        reporting_raw = AIOKafkaConsumer(
            TOPIC,
            bootstrap_servers=BOOTSTRAP,
            group_id="reporting",  # a new group: its own offsets, from the start
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await reporting_raw.start()
        try:
            reporting = AsyncKafkaConsumer(
                reporting_raw, event_registry, bus=reporting_bus
            )
            handled = await reporting.run_once(timeout_ms=5000)
        finally:
            await reporting_raw.stop()
        print(f"  {handled} events replayed: {' → '.join(read_model.timeline)}")
        print("  (a queue would have had nothing left to give it)")
    finally:
        await producer.stop()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
