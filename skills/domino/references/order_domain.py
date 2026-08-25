"""A complete DDD tour with `domino`: a small order-management domain.

Run it with::

    uv run python examples/order_domain.py

It exercises every building block: value objects, an aggregate root, domain
events, event handlers, an event bus, a repository, a unit of work, commands and
use cases (with correlation ids propagated automatically).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from domino import (
    AggregateRoot,
    Command,
    DomainEvent,
    DomainId,
    DomainNotFoundError,
    DomainStateError,
    DomainValidationError,
    EventBus,
    EventHandler,
    Repository,
    UnitOfWork,
    UseCase,
    ValueObject,
    configure,
)

# --- Value objects ---------------------------------------------------------


class Money(ValueObject):
    amount: Decimal
    currency: str  # ISO 4217, e.g. "EUR"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise DomainValidationError("Money amount cannot be negative")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise DomainValidationError(f"Invalid currency code: {self.currency}")

    def __is_currency_the_same(self, rhs: Money):
        if self.currency != rhs.currency:
            raise DomainValidationError("Cannot add different currencies")

    def __add__(self, other: Money) -> Money:
        self.__is_currency_the_same(other)
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, factor: int) -> Money:
        return Money(self.amount * factor, self.currency)


class Address(ValueObject):
    street: str
    city: str
    postal_code: str
    country: str  # ISO 3166-1 alpha-2


# --- Domain events ---------------------------------------------------------


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    customer_id: DomainId
    total: str


class OrderShipped(DomainEvent):
    order_id: DomainId


class OrderCancelled(DomainEvent):
    order_id: DomainId
    reason: str


# --- Aggregate root --------------------------------------------------------


class OrderStatus:
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    customer_id: DomainId = field(default_factory=DomainId.generate)
    items: list[dict] = field(default_factory=list)
    shipping_address: Address | None = None
    status: str = OrderStatus.DRAFT
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_item(self, name: str, quantity: int, unit_price: Money) -> None:
        if self.status != OrderStatus.DRAFT:
            raise DomainStateError("Cannot add items to a non-draft order")
        self.items.append(
            {"name": name, "quantity": quantity, "unit_price": unit_price}
        )
        self._touch()

    def total(self) -> Money:
        if not self.items:
            return Money(Decimal("0"), "EUR")
        currency = self.items[0]["unit_price"].currency
        amount = sum(
            (i["unit_price"].amount * i["quantity"] for i in self.items), Decimal("0")
        )
        return Money(amount, currency)

    def confirm(self) -> None:
        if self.status != OrderStatus.DRAFT:
            raise DomainStateError("Only draft orders can be confirmed")
        if not self.items:
            raise DomainStateError("Cannot confirm an order with no items")
        if self.shipping_address is None:
            raise DomainStateError("Cannot confirm without a shipping address")
        self.status = OrderStatus.CONFIRMED
        self._touch()
        self.log.info("confirmed, total %s EUR", self.total().amount)
        self._add_event(
            OrderConfirmed(
                order_id=self._id,
                customer_id=self.customer_id,
                total=str(self.total().amount),
            )
        )

    def ship(self) -> None:
        if self.status != OrderStatus.CONFIRMED:
            raise DomainStateError("Only confirmed orders can be shipped")
        self.status = OrderStatus.SHIPPED
        self._touch()
        self._add_event(OrderShipped(order_id=self._id))

    def cancel(self, reason: str) -> None:
        if self.status == OrderStatus.SHIPPED:
            raise DomainStateError("Cannot cancel a shipped order")
        self.status = OrderStatus.CANCELLED
        self._touch()
        self._add_event(OrderCancelled(order_id=self._id, reason=reason))


# --- Event handlers --------------------------------------------------------


# Handlers log through self.log — the class name and the correlation id are
# added automatically, so there is no plumbing to do. The two OrderConfirmed
# handlers share one id (same use case call); the OrderShipped handler shows a
# different one (a separate use case call).


class InventoryHandler(EventHandler):
    def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            self.log.info("reserving stock for order %s", event.order_id)


class EmailHandler(EventHandler):
    def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderConfirmed):
            self.log.info("confirmation sent to customer %s", event.customer_id)


class ShippingHandler(EventHandler):
    def handle(self, event: DomainEvent) -> None:
        if isinstance(event, OrderShipped):
            self.log.info("tracking generated for order %s", event.order_id)


# --- Repository (in-memory) ------------------------------------------------


class OrderRepository(Repository[Order]):
    def __init__(self) -> None:
        self._store: dict[DomainId, Order] = {}

    def get_by_id(self, id: DomainId) -> Order | None:
        return self._store.get(id)

    def save(self, aggregate: Order) -> None:
        self._store[aggregate.id] = aggregate

    def delete(self, id: DomainId) -> None:
        self._store.pop(id, None)


# --- Use case --------------------------------------------------------------


class PlaceOrderCommand(Command):
    customer_id: DomainId
    items: list[tuple[str, int, Money]]
    shipping_address: Address


class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    """Create and confirm an order, then publish its events after commit."""

    def execute(self, command: PlaceOrderCommand) -> DomainId:
        self.log.info("placing order for customer %s", command.customer_id)
        orders_repo = self._uow.repository("orders")
        order = Order(
            customer_id=command.customer_id,
            shipping_address=command.shipping_address,
        )
        for name, quantity, unit_price in command.items:
            order.add_item(name, quantity, unit_price)
        order.confirm()

        orders_repo.save(order)

        self._uow.enqueue_events(*order.pull_pending_events())
        return order.id


class ShipOrderCommand(Command):
    order_id: DomainId


class ShipOrder(UseCase[ShipOrderCommand, DomainId]):
    """Ship a confirmed order, then publish its events after commit."""

    def execute(self, command: ShipOrderCommand) -> DomainId:
        self.log.info("shipping order %s", command.order_id)
        orders_repo = self._uow.repository("orders")

        order = orders_repo.get_by_id(command.order_id)
        if order is None:
            raise DomainNotFoundError(f"Order {command.order_id} not found")

        order.ship()

        orders_repo.save(order)

        self._uow.enqueue_events(*order.pull_pending_events())
        return order.id


# --- Wiring ----------------------------------------------------------------


def main() -> None:
    # Configure Domino once, at startup: here, 16-char correlation ids for
    # tidier logs (a NanoID generator would plug in the same way).
    configure(correlation_id_factory=lambda: uuid4().hex[:16])

    # Domino logs through the "domino" logger; the app decides how to show it.
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-5s %(message)s", stream=sys.stdout
    )

    bus = EventBus()
    bus.register_all(
        [
            (OrderConfirmed, InventoryHandler()),
            (OrderConfirmed, EmailHandler()),
            (OrderShipped, ShippingHandler()),
        ]
    )

    uow = UnitOfWork(
        repositories={"orders": OrderRepository()},
        event_bus=bus,
    )

    print("--- placing order ---")
    with uow:
        order_id = PlaceOrder(uow).execute(
            PlaceOrderCommand(
                customer_id=DomainId.generate(),
                items=[
                    ("Mechanical keyboard", 1, Money(Decimal("150.00"), "EUR")),
                    ("USB-C hub", 2, Money(Decimal("35.00"), "EUR")),
                ],
                shipping_address=Address("123 Main St", "Paris", "75001", "FR"),
            )
        )
    order = uow.repository("orders").get_by_id(order_id)
    assert order is not None
    print(f"> order {order_id} is {order.status}, total {order.total().amount} EUR")

    print("--- shipping order ---")
    with uow:
        ShipOrder(uow).execute(ShipOrderCommand(order_id=order_id))

    order = uow.repository("orders").get_by_id(order_id)
    assert order is not None
    print(f"> order {order_id} is {order.status}")


if __name__ == "__main__":
    main()
