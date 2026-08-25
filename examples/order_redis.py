"""Two services, one trace: publishing to Redis Streams and consuming back.

Run it with::

    uv run --extra redis --extra sqlalchemy python examples/order_redis.py

The producer commits an order and stages its event in the outbox; a relay ships
that event to a Redis stream; a consumer group reads it back into a local event
bus. The correlation id opened by the use case travels with the event, so the
handler on the other side logs under the same trace.

Uses ``fakeredis`` (a dev dependency of this repository) so it runs with no
server. Point the client at a real ``redis.asyncio.Redis`` and nothing else
changes.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import field
from datetime import timedelta
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
from domino.integrations.redis import (
    AsyncRedisStreamConsumer,
    AsyncRedisStreamPublisher,
    to_envelope,
)
from domino.integrations.sqlalchemy import (
    AsyncOutboxRelay,
    AsyncSqlAlchemyRepository,
    AsyncSqlAlchemyUnitOfWork,
    DomainIdType,
    Outbox,
)

STREAM = "domino:orders"

# --- The contract both services share ---------------------------------------


class Money(ValueObject):
    amount: Decimal
    currency: str


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    total: Money


# Producer and consumer each register the types they exchange. Here one registry
# stands in for both; in real life it is the same code, imported on both sides.
event_registry = EventRegistry()
event_registry.register(OrderConfirmed)


# --- Producer: the ordering service -----------------------------------------


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    status: str = "draft"
    total: Money = field(default_factory=lambda: Money(Decimal("0"), "EUR"))

    def confirm(self) -> None:
        if self.status != "draft":
            raise DomainStateError("only a draft order can be confirmed")
        self.status = "confirmed"
        self.log.info("order confirmed for %s", self.total.amount)
        self._add_event(OrderConfirmed(order_id=self._id, total=self.total))


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


# --- Consumer: the warehouse service ----------------------------------------


class ReserveStock(AsyncEventHandler):
    async def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            # Logged in the producer's trace, with no id passed by hand.
            self.log.info("reserving stock for order %s", event.order_id)


# --- Demo -------------------------------------------------------------------


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-5s %(message)s",
        stream=sys.stdout,
    )
    configure(correlation_id_factory=lambda: "trace-42")  # readable ids for the demo

    try:
        import fakeredis.aioredis
    except ImportError:
        print("This demo needs fakeredis: uv sync --all-groups")
        print("Or point it at a real server with redis.asyncio.Redis().")
        return

    redis = fakeredis.aioredis.FakeRedis()

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    uow = AsyncSqlAlchemyUnitOfWork(
        session_factory, {"orders": OrderRepository}, outbox=outbox
    )

    # The producer side: the outbox relay is what actually talks to Redis.
    publisher = AsyncRedisStreamPublisher(
        redis, event_registry, stream=STREAM, maxlen=10_000
    )
    relay = AsyncOutboxRelay(session_factory, outbox, publisher=publisher)

    # The consumer side: its own bus, its own handlers, its own group.
    bus = AsyncEventBus()
    bus.register(OrderConfirmed, ReserveStock())
    consumer = AsyncRedisStreamConsumer(
        redis,
        event_registry,
        bus=bus,
        stream=STREAM,
        group="warehouse",
        consumer="worker-1",
        block_ms=0,
        dedupe_ttl=timedelta(hours=1),
    )
    await consumer.ensure_group()

    print("--- the ordering service confirms an order ---")
    order = Order(total=Money(Decimal("220.00"), "EUR"))
    async with uow:
        await uow.orders.save(order)
    async with uow:
        await ConfirmOrder(uow).execute(ConfirmOrderCommand(order_id=order.id))
    print("  committed; staged in the outbox, nothing on the stream yet")
    print(f"  stream length: {await redis.xlen(STREAM)}")

    print("--- the relay ships it to Redis ---")
    print(f"  {await relay.run_once()} event published")
    print(f"  stream length: {await redis.xlen(STREAM)}")

    print("--- the warehouse service consumes it ---")
    print(f"  {await consumer.run_once()} event handled")

    print("--- a redelivery is skipped, thanks to dedupe_ttl ---")
    # Read the entry back off the stream and publish it again, exactly as a
    # relay would after crashing between the publish and the acknowledgement.
    entries = await redis.xrange(STREAM)
    fields = entries[0][1] if entries else None
    assert fields is not None, "the relay published one entry just above"
    replayed = event_registry.decode(to_envelope(fields))
    await publisher.publish(replayed)
    print(f"  stream length: {await redis.xlen(STREAM)} (the duplicate is there)")
    print(f"  {await consumer.run_once()} event handled: the consumer skipped it")

    print("--- nothing left pending ---")
    pending = await redis.xpending(STREAM, "warehouse")
    print(f"  pending entries: {pending['pending']}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
