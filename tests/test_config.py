"""Tests for central configuration (configure / get_config / reset_config)."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest

from domino import (
    DomainEvent,
    DomainId,
    configure,
    correlation_scope,
    get_config,
    get_correlation_id,
    new_correlation_id,
    reset_config,
)


@pytest.fixture(autouse=True)
def _reset_config() -> Iterator[None]:
    reset_config()
    yield
    reset_config()


class Ping(DomainEvent):
    pass


class TestDefaults:
    def test_default_correlation_id_is_uuid_hex(self):
        assert len(new_correlation_id()) == 32  # uuid4().hex

    def test_default_domain_id_is_uuid(self):
        assert isinstance(DomainId.generate().value, UUID)


class TestConfigureCorrelationId:
    def test_overrides_generated_id(self):
        configure(correlation_id_factory=lambda: "FIXED-CID")
        with correlation_scope() as cid:
            assert cid == "FIXED-CID"
            assert get_correlation_id() == "FIXED-CID"

    def test_flows_into_events(self):
        configure(correlation_id_factory=lambda: "sixteencharslong")
        with correlation_scope():
            event = Ping()
        assert event.correlation_id == "sixteencharslong"

    def test_sixteen_char_example(self):
        from uuid import uuid4

        configure(correlation_id_factory=lambda: uuid4().hex[:16])
        assert len(new_correlation_id()) == 16


class TestConfigureIdFactory:
    def test_overrides_domain_id_generation(self):
        counter = {"n": 0}

        def next_id() -> str:
            counter["n"] += 1
            return f"ID-{counter['n']}"

        configure(id_factory=next_id)
        assert DomainId.generate().value == "ID-1"
        assert DomainId.generate().value == "ID-2"


class TestReset:
    def test_configure_is_partial(self):
        configure(correlation_id_factory=lambda: "X")
        configure(id_factory=lambda: "Y")  # does not clear the previous setting
        assert new_correlation_id() == "X"
        assert DomainId.generate().value == "Y"

    def test_reset_restores_defaults(self):
        configure(correlation_id_factory=lambda: "X", id_factory=lambda: "Y")
        reset_config()
        assert len(new_correlation_id()) == 32
        assert isinstance(DomainId.generate().value, UUID)

    def test_get_config_exposes_factories(self):
        configure(correlation_id_factory=lambda: "Z")
        assert get_config().correlation_id_factory() == "Z"
