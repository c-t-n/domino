"""Tests for encoding domain events to envelopes and back."""

from __future__ import annotations

from dataclasses import field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from ipaddress import IPv4Address
from uuid import UUID, uuid4

import pytest

from domino.core.correlation import correlation_scope
from domino.core.entity import Entity
from domino.core.id import DomainId
from domino.core.value_object import ValueObject
from domino.events.domain_event import DomainEvent
from domino.events.serialization import EventRegistry, SerializationError


class Money(ValueObject):
    amount: Decimal
    currency: str


class Priority(Enum):
    LOW = "low"
    HIGH = "high"


class OrderLine(Entity):
    _id: DomainId = field(default_factory=DomainId.generate)
    product: str = ""
    quantity: int = 0


class OrderConfirmed(DomainEvent):
    order_id: DomainId
    total: Money
    confirmed_on: date
    priority: Priority = Priority.LOW
    tags: list[str] = field(default_factory=list)
    note: str | None = None


class OrderShipped(DomainEvent):
    order_id: DomainId


@pytest.fixture
def registry() -> EventRegistry:
    r = EventRegistry()
    r.register_all([OrderConfirmed, OrderShipped])
    return r


def _order_confirmed(
    *,
    order_id: DomainId | None = None,
    total: Money | None = None,
    confirmed_on: date = date(2026, 8, 25),
    priority: Priority = Priority.HIGH,
    tags: list[str] | None = None,
    note: str | None = None,
) -> OrderConfirmed:
    return OrderConfirmed(
        order_id=order_id if order_id is not None else DomainId.generate(),
        total=total if total is not None else Money(Decimal("42.50"), "EUR"),
        confirmed_on=confirmed_on,
        priority=priority,
        tags=["gift", "express"] if tags is None else tags,
        note=note,
    )


class TestRegistration:
    def test_name_defaults_to_the_class_name(self, registry):
        assert registry.name_for(OrderConfirmed) == "OrderConfirmed"
        assert registry.type_for("OrderConfirmed") is OrderConfirmed

    def test_explicit_name(self):
        registry = EventRegistry()
        registry.register(OrderConfirmed, name="orders.OrderConfirmed.v2")
        assert registry.name_for(OrderConfirmed) == "orders.OrderConfirmed.v2"
        assert registry.encode(_order_confirmed())["event_name"] == (
            "orders.OrderConfirmed.v2"
        )

    def test_register_returns_the_type_so_it_can_decorate(self):
        registry = EventRegistry()
        assert registry.register(OrderShipped) is OrderShipped

    def test_registering_the_same_type_twice_is_idempotent(self, registry):
        registry.register(OrderConfirmed)
        assert registry.type_for("OrderConfirmed") is OrderConfirmed

    def test_two_types_under_one_name_is_refused(self, registry):
        class OrderConfirmed(DomainEvent):  # a clashing name from another context
            other: str

        with pytest.raises(SerializationError, match="already registered"):
            registry.register(OrderConfirmed)

    def test_encoding_an_unregistered_event_names_the_fix(self):
        with pytest.raises(SerializationError, match="register"):
            EventRegistry().encode(_order_confirmed())

    def test_decoding_an_unknown_name_lists_what_is_registered(self, registry):
        with pytest.raises(SerializationError, match="OrderConfirmed, OrderShipped"):
            registry.decode({"event_name": "Nope", "payload": {}})


class TestRoundTrip:
    def test_payload_survives(self, registry):
        event = _order_confirmed(note="fragile")
        assert registry.decode(registry.encode(event)) == event

    def test_envelope_fields_survive(self, registry):
        with correlation_scope("trace-1"):
            event = _order_confirmed()
        decoded = registry.decode(registry.encode(event))
        assert decoded.event_id == event.event_id
        assert decoded.occurred_on == event.occurred_on
        assert decoded.correlation_id == "trace-1"

    def test_json_round_trip(self, registry):
        event = _order_confirmed()
        assert registry.decode_json(registry.encode_json(event)) == event

    def test_types_are_rebuilt_not_left_as_strings(self, registry):
        decoded = registry.decode(registry.encode(_order_confirmed()))
        assert isinstance(decoded, OrderConfirmed)
        assert isinstance(decoded.order_id, DomainId)
        assert isinstance(decoded.total, Money)
        assert isinstance(decoded.total.amount, Decimal)
        assert isinstance(decoded.confirmed_on, date)
        assert decoded.priority is Priority.HIGH

    def test_decimals_keep_their_precision(self, registry):
        event = _order_confirmed(total=Money(Decimal("0.1"), "EUR"))
        decoded = registry.decode(registry.encode(event))
        assert decoded.total.amount == Decimal("0.1")  # not 0.1000000000000000055

    def test_string_backed_domain_id(self, registry):
        event = OrderShipped(order_id=DomainId("ORD-2024-001"))
        decoded = registry.decode(registry.encode(event))
        assert decoded.order_id == DomainId("ORD-2024-001")

    def test_uuid_backed_domain_id_stays_a_uuid(self, registry):
        raw = uuid4()
        decoded = registry.decode(registry.encode(OrderShipped(order_id=DomainId(raw))))
        assert decoded.order_id.value == raw

    def test_optional_field_left_none(self, registry):
        decoded = registry.decode(registry.encode(_order_confirmed(note=None)))
        assert decoded.note is None

    def test_empty_collection(self, registry):
        decoded = registry.decode(registry.encode(_order_confirmed(tags=[])))
        assert decoded.tags == []


class TestEnvelopeShape:
    def test_envelope_is_json_serializable_as_is(self, registry):
        envelope = registry.encode(_order_confirmed())
        assert set(envelope) == {
            "event_name",
            "event_id",
            "occurred_on",
            "correlation_id",
            "payload",
        }
        assert envelope["payload"]["total"] == {"amount": "42.50", "currency": "EUR"}
        assert envelope["payload"]["priority"] == "high"

    def test_base_fields_are_not_repeated_in_the_payload(self, registry):
        payload = registry.encode(_order_confirmed())["payload"]
        assert not {"event_id", "occurred_on", "correlation_id"} & set(payload)

    def test_timestamps_are_iso_8601(self, registry):
        event = _order_confirmed()
        envelope = registry.encode(event)
        assert datetime.fromisoformat(envelope["occurred_on"]) == event.occurred_on
        assert envelope["payload"]["confirmed_on"] == "2026-08-25"


class TestTolerance:
    def test_unknown_payload_keys_are_ignored(self, registry):
        # A producer added a field; an older consumer must keep working.
        envelope = registry.encode(_order_confirmed())
        envelope["payload"]["shipping_method"] = "drone"
        assert registry.decode(envelope).order_id is not None

    def test_missing_optional_field_falls_back_to_the_default(self, registry):
        envelope = registry.encode(_order_confirmed())
        del envelope["payload"]["priority"]
        assert registry.decode(envelope).priority is Priority.LOW

    def test_missing_required_field_is_reported_with_the_event_name(self, registry):
        envelope = registry.encode(_order_confirmed())
        del envelope["payload"]["order_id"]
        with pytest.raises(SerializationError, match="cannot rebuild OrderConfirmed"):
            registry.decode(envelope)

    def test_undecodable_value_names_the_field(self, registry):
        envelope = registry.encode(_order_confirmed())
        envelope["payload"]["confirmed_on"] = "not-a-date"
        with pytest.raises(
            SerializationError, match=r"cannot decode OrderConfirmed\.confirmed_on"
        ):
            registry.decode(envelope)

    def test_envelope_without_a_name(self, registry):
        with pytest.raises(SerializationError, match="event_name"):
            registry.decode({"payload": {}})

    def test_invalid_json(self, registry):
        with pytest.raises(SerializationError, match="not valid JSON"):
            registry.decode_json("{nope")

    def test_json_that_is_not_an_object(self, registry):
        with pytest.raises(SerializationError, match="must be a JSON object"):
            registry.decode_json("[1, 2]")


class TestCustomCodecs:
    def test_unsupported_type_points_at_register_codec(self, registry):
        class Connected(DomainEvent):
            address: IPv4Address

        registry.register(Connected)
        with pytest.raises(SerializationError, match="register_codec"):
            registry.encode(Connected(address=IPv4Address("10.0.0.1")))

    def test_registered_codec_round_trips(self, registry):
        class Connected(DomainEvent):
            address: IPv4Address

        registry.register(Connected)
        registry.register_codec(IPv4Address, str, IPv4Address)

        event = Connected(address=IPv4Address("10.0.0.1"))
        decoded = registry.decode(registry.encode(event))
        assert decoded.address == event.address
        assert isinstance(decoded.address, IPv4Address)


class TestNestedStructures:
    def test_entity_inside_an_event(self, registry):
        class LineAdded(DomainEvent):
            line: OrderLine

        registry.register(LineAdded)
        event = LineAdded(line=OrderLine(product="Keyboard", quantity=2))
        decoded = registry.decode(registry.encode(event))
        assert isinstance(decoded.line, OrderLine)
        assert decoded.line.product == "Keyboard"
        assert decoded.line.id == event.line.id

    def test_list_of_value_objects(self, registry):
        class Refunded(DomainEvent):
            amounts: list[Money]

        registry.register(Refunded)
        event = Refunded(
            amounts=[Money(Decimal("1.10"), "EUR"), Money(Decimal("2"), "USD")]
        )
        decoded = registry.decode(registry.encode(event))
        assert decoded.amounts == event.amounts
        assert all(isinstance(m.amount, Decimal) for m in decoded.amounts)

    def test_mapping_values_are_decoded(self, registry):
        class Priced(DomainEvent):
            by_region: dict[str, Money]

        registry.register(Priced)
        event = Priced(by_region={"eu": Money(Decimal("10.00"), "EUR")})
        decoded = registry.decode(registry.encode(event))
        assert decoded.by_region == event.by_region

    def test_plain_uuid_and_datetime_fields(self, registry):
        class Audited(DomainEvent):
            actor: UUID
            at: datetime

        registry.register(Audited)
        event = Audited(actor=uuid4(), at=datetime.now(UTC))
        decoded = registry.decode(registry.encode(event))
        assert decoded.actor == event.actor
        assert decoded.at == event.at
