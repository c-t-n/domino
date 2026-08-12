"""Tests for the core building blocks: Entity, ValueObject, DomainId, Result."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, field
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from domino.core.domain_error import (
    DomainError,
    DomainNotFoundError,
    DomainStateError,
    DomainValidationError,
)
from domino.core.entity import Entity
from domino.core.id import DomainId
from domino.core.result import Failure, Success, failure, success
from domino.core.value_object import ValueObject

# --- DomainError ---


class TestDomainError:
    def test_default_code_is_class_name(self):
        assert DomainError("boom").code == "DomainError"

    def test_custom_code(self):
        assert DomainError("boom", code="CUSTOM").code == "CUSTOM"

    def test_message_accessible(self):
        assert DomainError("my message").message == "my message"

    def test_subclass_codes(self):
        assert DomainValidationError("bad").code == "VALIDATION_ERROR"
        assert DomainStateError("nope").code == "STATE_ERROR"
        assert DomainNotFoundError("missing").code == "NOT_FOUND"

    def test_equality_and_hash(self):
        assert DomainError("a") == DomainError("a")
        assert DomainError("a") != DomainError("b")
        assert DomainValidationError("a") != DomainError("a")
        assert hash(DomainError("a")) == hash(DomainError("a"))


# --- DomainId ---


class TestDomainId:
    def test_generate_is_unique(self):
        assert DomainId.generate() != DomainId.generate()

    def test_from_uuid(self):
        u = uuid4()
        assert DomainId(u).value == u

    def test_from_string(self):
        assert DomainId("ORD-2024-001").value == "ORD-2024-001"

    def test_equality_and_hash(self):
        u = uuid4()
        assert DomainId(u) == DomainId(u)
        assert hash(DomainId(u)) == hash(DomainId(u))

    def test_empty_uuid_is_empty(self):
        assert DomainId.empty().is_empty() is True
        assert DomainId(UUID(int=0)).is_empty() is True
        assert DomainId.generate().is_empty() is False

    def test_empty_string_is_empty(self):
        assert DomainId("").is_empty() is True
        assert DomainId("ORD-1").is_empty() is False

    def test_invalid_type(self):
        with pytest.raises(TypeError):
            DomainId(123)  # ty: ignore[invalid-argument-type]

    def test_sortable(self):
        ids = sorted([DomainId("b"), DomainId("a"), DomainId("c")])
        assert [str(i) for i in ids] == ["a", "b", "c"]


# --- ValueObject ---


class Money(ValueObject):
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise DomainValidationError("Amount cannot be negative")

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise DomainValidationError("Cannot add different currencies")
        return Money(self.amount + other.amount, self.currency)


class TestValueObject:
    def test_equality(self):
        assert Money(Decimal("10.00"), "EUR") == Money(Decimal("10.00"), "EUR")

    def test_inequality(self):
        assert Money(Decimal("10.00"), "EUR") != Money(Decimal("20.00"), "EUR")

    def test_hash_consistency(self):
        assert hash(Money(Decimal("10"), "EUR")) == hash(Money(Decimal("10"), "EUR"))

    def test_usable_as_dict_key(self):
        prices = {Money(Decimal("10"), "EUR"): "cheap"}
        assert prices[Money(Decimal("10"), "EUR")] == "cheap"

    def test_immutable(self):
        m = Money(Decimal("10.00"), "EUR")
        with pytest.raises(FrozenInstanceError):
            m.amount = Decimal("20.00")  # ty: ignore[invalid-assignment]

    def test_replace_returns_new_instance(self):
        m = Money(Decimal("10.00"), "EUR")
        m2 = m.replace(amount=Decimal("20.00"))
        assert m2 == Money(Decimal("20.00"), "EUR")
        assert m.amount == Decimal("10.00")  # original untouched

    def test_replace_revalidates(self):
        with pytest.raises(DomainValidationError):
            Money(Decimal("10.00"), "EUR").replace(amount=Decimal("-1"))

    def test_validation_on_construction(self):
        with pytest.raises(DomainValidationError):
            Money(Decimal("-1.00"), "EUR")

    def test_repr(self):
        assert "Money" in repr(Money(Decimal("10.00"), "EUR"))


# --- Entity ---


class SampleEntity(Entity):
    _id: DomainId = field(default_factory=DomainId.generate)
    name: str = ""


class TestEntity:
    def test_equality_is_by_id(self):
        i = DomainId.generate()
        assert SampleEntity(_id=i, name="first") == SampleEntity(_id=i, name="second")

    def test_inequality_by_id(self):
        assert SampleEntity(name="a") != SampleEntity(name="a")

    def test_hash_by_id(self):
        i = DomainId.generate()
        assert hash(SampleEntity(_id=i)) == hash(SampleEntity(_id=i))

    def test_is_transient_when_id_empty(self):
        assert SampleEntity(_id=DomainId.empty()).is_transient() is True
        assert SampleEntity().is_transient() is False

    def test_id_property(self):
        i = DomainId.generate()
        assert SampleEntity(_id=i).id == i

    def test_repr(self):
        assert "SampleEntity" in repr(SampleEntity())


# --- Result ---


class TestResult:
    def test_success_value(self):
        s = success(42)
        assert s.is_success() and not s.is_failure()
        assert s.unwrap() == 42

    def test_success_map(self):
        result = success(42).map(lambda x: x * 2)
        assert isinstance(result, Success)
        assert result.unwrap() == 84

    def test_success_bind(self):
        assert success(42).bind(lambda x: success(x * 2)).unwrap() == 84

    def test_failure_error(self):
        err = DomainError("oops")
        f = failure(err)
        assert f.is_failure() and not f.is_success()
        assert f.unwrap_error() == err

    def test_failure_unwrap_raises(self):
        with pytest.raises(DomainValidationError):
            failure(DomainValidationError("bad")).unwrap()

    def test_failure_map_is_noop(self):
        f: Failure = failure(DomainError("oops"))
        assert f.map(lambda x: x * 2) == f

    def test_failure_map_error(self):
        mapped = failure(DomainError("oops")).map_error(
            lambda e: DomainStateError(e.message)
        )
        assert mapped.unwrap_error().code == "STATE_ERROR"

    def test_unwrap_or(self):
        assert failure(DomainError("oops")).unwrap_or("default") == "default"
        assert success(1).unwrap_or(0) == 1

    def test_unwrap_or_else(self):
        assert failure(DomainStateError("x")).unwrap_or_else(lambda e: e.code) == (
            "STATE_ERROR"
        )

    def test_success_unwrap_error_raises(self):
        with pytest.raises(RuntimeError):
            success(42).unwrap_error()

    def test_equality(self):
        assert success(42) == success(42)
        assert failure(DomainError("a")) == failure(DomainError("a"))
        assert success(1) != failure(DomainError("a"))
