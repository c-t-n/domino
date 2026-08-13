"""Tests for the optional SQLAlchemy integration (domino.sqlalchemy)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import field
from decimal import Decimal

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    create_engine,
    select,
)
from sqlalchemy.orm import (
    Session,
    composite,
    registry,
    relationship,
    sessionmaker,
)

from domino import (
    AggregateRoot,
    DomainEvent,
    DomainId,
    DomainStateError,
    Entity,
    ValueObject,
    eq,
    ge,
    gt,
    in_,
    like,
    ne,
)
from domino.sqlalchemy import (
    DomainIdType,
    Filterable,
    SqlAlchemyRepository,
    SqlAlchemyUnitOfWork,
)

# --- Domain (pure Domino) ---------------------------------------------------


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
    priority: int = 0

    def add_line(self, product: str, quantity: int, unit_price: Money) -> None:
        self.lines.append(
            OrderLine(product=product, quantity=quantity, unit_price=unit_price)
        )

    def total(self) -> Money:
        return sum((line.subtotal() for line in self.lines), Money(Decimal("0"), "EUR"))

    def confirm(self) -> None:
        if not self.lines:
            raise DomainStateError("cannot confirm an empty order")
        self.status = "confirmed"
        self._add_event(OrderConfirmed(order_id=self._id))


# --- Infrastructure: tables + imperative mapping (once, at import) ----------

metadata = MetaData()
mapper_registry = registry()

orders_table = Table(
    "orders",
    metadata,
    Column("id", DomainIdType, primary_key=True),
    Column("customer_id", DomainIdType, nullable=False),
    Column("status", String(20), nullable=False),
    Column("priority", Integer, nullable=False),
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


class OrderRepository(SqlAlchemyRepository[Order], Filterable[Order]):
    def by_customer(self, customer_id: DomainId) -> list[Order]:
        # Reference the Table column (typed) rather than the ORM attribute, which
        # imperative mapping doesn't surface to type checkers.
        query = select(Order).where(orders_table.c.customer_id == customer_id)
        return list(self._session.scalars(query))


@pytest.fixture
def session_factory() -> Callable[[], Session]:
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    return sessionmaker(engine)


def _sample_order(customer_id: DomainId | None = None) -> Order:
    order = Order(customer_id=customer_id or DomainId.generate())
    order.add_line("Keyboard", 1, Money(Decimal("150.00"), "EUR"))
    order.add_line("USB-C hub", 2, Money(Decimal("35.00"), "EUR"))
    return order


class TestDomainIdType:
    def test_uuid_id_round_trips(self, session_factory):
        order = _sample_order()
        oid = order.id
        with session_factory() as s:
            s.add(order)
            s.commit()
        with session_factory() as s:
            loaded = s.get(Order, oid)
            assert loaded is not None
            assert loaded.id == oid
            assert isinstance(loaded.id.value, type(oid.value))

    def test_string_id_round_trips(self, session_factory):
        order = Order(_id=DomainId("ORD-2024-001"))
        order.add_line("Keyboard", 1, Money(Decimal("10"), "EUR"))
        with session_factory() as s:
            s.add(order)
            s.commit()
        with session_factory() as s:
            loaded = s.get(Order, DomainId("ORD-2024-001"))
            assert loaded is not None
            assert loaded.id == DomainId("ORD-2024-001")


class TestSqlAlchemyRepository:
    def test_infers_aggregate_type(self):
        assert OrderRepository.aggregate_type is Order

    def test_save_and_get_round_trip(self, session_factory):
        order = _sample_order()
        oid = order.id
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            uow.orders.save(order)
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            loaded = uow.orders.get_by_id(oid)
            assert isinstance(loaded, Order)
            assert len(loaded.lines) == 2
            assert loaded.lines[0].unit_price == Money(Decimal("150.00"), "EUR")
            assert loaded.total() == Money(Decimal("220.00"), "EUR")

    def test_get_missing_returns_none(self, session_factory):
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            assert uow.orders.get_by_id(DomainId.generate()) is None

    def test_delete(self, session_factory):
        order = _sample_order()
        oid = order.id
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            uow.orders.save(order)
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            uow.orders.delete(oid)
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            assert uow.orders.get_by_id(oid) is None

    def test_custom_finder(self, session_factory):
        customer = DomainId.generate()
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            uow.orders.save(_sample_order(customer))
            uow.orders.save(_sample_order(customer))
            uow.orders.save(_sample_order())  # different customer
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            assert len(uow.orders.by_customer(customer)) == 2

    def test_explicit_aggregate_type_overrides_inference(self):
        class Weird(SqlAlchemyRepository[Order]):
            aggregate_type = Order  # explicit still works

        assert Weird.aggregate_type is Order


class TestSqlAlchemyUnitOfWork:
    def test_commits_on_clean_exit(self, session_factory):
        order = _sample_order()
        oid = order.id
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            uow.orders.save(order)
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            assert uow.orders.get_by_id(oid) is not None

    def test_rolls_back_on_error(self, session_factory):
        order = _sample_order()
        oid = order.id
        uow = SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository})
        with pytest.raises(ValueError), uow:
            uow.orders.save(order)
            raise ValueError("boom")
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            assert uow.orders.get_by_id(oid) is None

    def test_session_only_available_in_scope(self, session_factory):
        uow = SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository})
        with pytest.raises(RuntimeError):
            _ = uow.session
        with uow:
            assert uow.session is not None
        with pytest.raises(RuntimeError):
            _ = uow.session

    def test_fresh_session_per_scope(self, session_factory):
        uow = SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository})
        with uow:
            first = uow.session
        with uow:
            assert uow.session is not first

    def test_unknown_repository_raises(self, session_factory):
        with (
            SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow,
            pytest.raises(AttributeError),
        ):
            _ = uow.customers

    def test_loaded_aggregate_has_no_stale_events(self, session_factory):
        order = _sample_order()
        order.confirm()  # records an event
        oid = order.id
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            uow.orders.save(order)
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            loaded = uow.orders.get_by_id(oid)
            assert loaded is not None
            assert not loaded.has_pending_events()


def _order(status: str = "draft", priority: int = 0) -> Order:
    order = Order(status=status, priority=priority)
    order.add_line("Widget", 1, Money(Decimal("10"), "EUR"))
    return order


class TestFilterable:
    @pytest.fixture
    def seeded(self, session_factory: Callable[[], Session]) -> Callable[[], Session]:
        # statuses/priorities: confirmed/5, confirmed/1, draft/9, cancelled/0
        with SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository}) as uow:
            uow.orders.save(_order("confirmed", 5))
            uow.orders.save(_order("confirmed", 1))
            uow.orders.save(_order("draft", 9))
            uow.orders.save(_order("cancelled", 0))
        return session_factory

    def _repo(self, factory: Callable[[], Session]) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(factory, {"orders": OrderRepository})

    def test_list_all(self, seeded):
        with self._repo(seeded) as uow:
            assert len(uow.orders.list()) == 4

    def test_eq(self, seeded):
        with self._repo(seeded) as uow:
            assert len(uow.orders.list(eq("status", "confirmed"))) == 2

    def test_ne(self, seeded):
        with self._repo(seeded) as uow:
            assert len(uow.orders.list(ne("status", "confirmed"))) == 2

    def test_in(self, seeded):
        with self._repo(seeded) as uow:
            assert len(uow.orders.list(in_("status", ["draft", "cancelled"]))) == 2

    def test_like(self, seeded):
        with self._repo(seeded) as uow:
            # matches confirmed (x2) and cancelled
            assert len(uow.orders.list(like("status", "c%"))) == 3

    def test_comparisons(self, seeded):
        with self._repo(seeded) as uow:
            assert len(uow.orders.list(gt("priority", 4))) == 2  # 5, 9
            assert len(uow.orders.list(ge("priority", 5))) == 2  # 5, 9

    def test_multiple_specs_are_anded(self, seeded):
        with self._repo(seeded) as uow:
            found = uow.orders.list(eq("status", "confirmed"), gt("priority", 3))
            assert len(found) == 1  # only confirmed/5

    def test_or(self, seeded):
        with self._repo(seeded) as uow:
            spec = eq("status", "draft") | eq("status", "cancelled")
            assert len(uow.orders.list(spec)) == 2

    def test_not(self, seeded):
        with self._repo(seeded) as uow:
            assert len(uow.orders.list(~eq("status", "confirmed"))) == 2

    def test_same_spec_in_memory_and_in_sql(self, seeded):
        spec = eq("status", "confirmed") & gt("priority", 3)
        with self._repo(seeded) as uow:
            rows = uow.orders.list(spec)
            assert len(rows) == 1
            assert all(spec.is_satisfied_by(order) for order in rows)
            # cross-check against evaluating the spec in memory over all rows
            in_memory = [o for o in uow.orders.list() if spec.is_satisfied_by(o)]
            assert len(in_memory) == 1
