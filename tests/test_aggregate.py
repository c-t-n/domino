"""Tests for AggregateRoot and its domain-event recording."""

from __future__ import annotations

from dataclasses import field
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from domino.aggregate.aggregate_root import AggregateRoot
from domino.core.domain_error import DomainStateError
from domino.core.id import DomainId
from domino.core.value_object import ValueObject
from domino.events.domain_event import DomainEvent


class Money(ValueObject):
    amount: Decimal
    currency: str

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError("Currency mismatch")
        return Money(self.amount + other.amount, self.currency)


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    total: str


class OrderCancelled(DomainEvent):
    order_id: DomainId
    reason: str


class OrderStatus:
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    customer_id: DomainId = field(default_factory=DomainId.generate)
    items: list = field(default_factory=list)
    status: str = OrderStatus.DRAFT
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_item(self, product_id: str, quantity: int, price: Money) -> None:
        if self.status != OrderStatus.DRAFT:
            raise DomainStateError("Cannot modify a non-draft order")
        self.items.append(
            {"product_id": product_id, "quantity": quantity, "price": price}
        )
        self._touch()

    def total(self) -> Money:
        if not self.items:
            return Money(Decimal("0"), "EUR")
        currency = self.items[0]["price"].currency
        amount = sum(
            (i["price"].amount * i["quantity"] for i in self.items), Decimal("0")
        )
        return Money(amount, currency)

    def confirm(self) -> None:
        if self.status != OrderStatus.DRAFT:
            raise DomainStateError("Only draft orders can be confirmed")
        if not self.items:
            raise DomainStateError("Cannot confirm an empty order")
        self.status = OrderStatus.CONFIRMED
        self._touch()
        self._add_event(
            OrderConfirmed(order_id=self._id, total=str(self.total().amount))
        )

    def cancel(self, reason: str) -> None:
        if self.status == OrderStatus.CONFIRMED:
            raise DomainStateError("Cannot cancel a confirmed order")
        self.status = OrderStatus.CANCELLED
        self._touch()
        self._add_event(OrderCancelled(order_id=self._id, reason=reason))


class TestAggregateRoot:
    def test_new_order_has_no_pending_events(self):
        order = Order()
        assert order.status == OrderStatus.DRAFT
        assert order.has_pending_events() is False

    def test_identity_equality(self):
        i = DomainId.generate()
        assert Order(_id=i, status="draft") == Order(_id=i, status="confirmed")
        assert Order() != Order()

    def test_add_item(self):
        order = Order()
        order.add_item("PROD-1", 2, Money(Decimal("10.00"), "EUR"))
        order.add_item("PROD-2", 1, Money(Decimal("25.00"), "EUR"))
        assert len(order.items) == 2

    def test_total(self):
        order = Order()
        order.add_item("PROD-1", 2, Money(Decimal("10.00"), "EUR"))
        order.add_item("PROD-2", 1, Money(Decimal("25.00"), "EUR"))
        assert order.total() == Money(Decimal("45.00"), "EUR")

    def test_confirm_records_event(self):
        order = Order()
        order.add_item("PROD-1", 1, Money(Decimal("10.00"), "EUR"))
        order.confirm()
        assert order.status == OrderStatus.CONFIRMED
        assert order.has_pending_events() is True

    def test_pull_pending_events_clears_them(self):
        order = Order()
        order.add_item("PROD-1", 1, Money(Decimal("10.00"), "EUR"))
        order.confirm()
        events = order.pull_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], OrderConfirmed)
        assert isinstance(events[0].event_id, type(events[0].event_id))
        assert order.has_pending_events() is False
        assert order.pull_pending_events() == []

    def test_cancel_records_event(self):
        order = Order()
        order.add_item("PROD-1", 1, Money(Decimal("10.00"), "EUR"))
        order.cancel("Customer request")
        assert order.status == OrderStatus.CANCELLED
        events = order.pull_pending_events()
        assert isinstance(events[0], OrderCancelled)

    def test_modifying_non_draft_fails(self):
        order = Order()
        order.add_item("PROD-1", 1, Money(Decimal("10.00"), "EUR"))
        order.confirm()
        with pytest.raises(DomainStateError):
            order.add_item("PROD-2", 1, Money(Decimal("5.00"), "EUR"))

    def test_empty_order_cannot_confirm(self):
        with pytest.raises(DomainStateError):
            Order().confirm()

    def test_touch_updates_timestamp(self):
        order = Order()
        before = order.updated_at
        order.add_item("PROD-1", 1, Money(Decimal("10.00"), "EUR"))
        assert order.updated_at >= before

    def test_touch_updates_a_falsy_timestamp(self):
        # Regression: guarding on the *value* skipped the refresh whenever the
        # current timestamp was falsy (None on a not-yet-persisted aggregate).
        class Draft(AggregateRoot):
            _id: DomainId = field(default_factory=DomainId.generate)
            updated_at: datetime | None = None

            def edit(self) -> None:
                self._touch()

        draft = Draft()
        draft.edit()
        assert isinstance(draft.updated_at, datetime)

    def test_touch_is_a_noop_without_the_field(self):
        # Regression: the aggregate has no updated_at, so _touch() must neither
        # raise nor invent an attribute outside the dataclass.
        class Tag(AggregateRoot):
            _id: DomainId = field(default_factory=DomainId.generate)
            label: str = ""

            def rename(self, label: str) -> None:
                self.label = label
                self._touch()

        tag = Tag()
        tag.rename("urgent")
        assert tag.label == "urgent"
        assert not hasattr(tag, "updated_at")

    def test_repr_excludes_internal_events(self):
        order = Order()
        order.add_item("PROD-1", 1, Money(Decimal("10.00"), "EUR"))
        order.confirm()
        text = repr(order)
        assert "Order" in text
        assert "_domain_events" not in text  # managed internally, not a field
