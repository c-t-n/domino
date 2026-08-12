"""Tests for ambient correlation-id propagation."""

from __future__ import annotations

from domino import (
    Command,
    DomainEvent,
    UseCase,
    correlation_scope,
    get_correlation_id,
    new_correlation_id,
)


class Ping(DomainEvent):
    pass


class DoThing(Command):
    value: int


# --- The contextvar primitive ---


class TestCorrelationScope:
    def test_no_scope_returns_none(self):
        assert get_correlation_id() is None

    def test_scope_sets_and_resets(self):
        with correlation_scope() as cid:
            assert cid
            assert get_correlation_id() == cid
        assert get_correlation_id() is None

    def test_scope_accepts_explicit_id(self):
        with correlation_scope("trace-123") as cid:
            assert cid == "trace-123"
            assert get_correlation_id() == "trace-123"

    def test_nested_scopes_restore_outer(self):
        with correlation_scope("outer"):
            with correlation_scope("inner"):
                assert get_correlation_id() == "inner"
            assert get_correlation_id() == "outer"
        assert get_correlation_id() is None

    def test_new_correlation_id_is_unique(self):
        assert new_correlation_id() != new_correlation_id()


# --- Events capture the ambient id ---


class TestEventCorrelation:
    def test_event_captures_ambient_id(self):
        with correlation_scope("abc"):
            event = Ping()
        assert event.correlation_id == "abc"

    def test_event_without_scope_has_none(self):
        assert Ping().correlation_id is None

    def test_events_in_same_scope_share_the_id(self):
        with correlation_scope() as cid:
            assert Ping().correlation_id == cid
            assert Ping().correlation_id == cid


# --- Use cases open a scope automatically ---


class RecordingUseCase(UseCase[DoThing, str]):
    def __init__(self) -> None:
        self.seen_cid: str | None = None
        self.event_cid: str | None = None

    def execute(self, command: DoThing) -> str:
        self.seen_cid = get_correlation_id()
        self.event_cid = Ping().correlation_id
        return "ok"


class TestUseCaseCorrelation:
    def test_scope_is_opened_automatically(self):
        uc = RecordingUseCase()
        assert get_correlation_id() is None

        uc.execute(DoThing(value=1))

        assert uc.seen_cid is not None
        assert uc.event_cid == uc.seen_cid  # the event captured the same id
        assert get_correlation_id() is None  # and it was cleaned up afterwards

    def test_each_top_level_call_gets_a_new_id(self):
        uc = RecordingUseCase()
        uc.execute(DoThing(value=1))
        first = uc.seen_cid
        uc.execute(DoThing(value=2))
        assert uc.seen_cid != first

    def test_nested_use_case_reuses_outer_id(self):
        uc = RecordingUseCase()
        with correlation_scope("outer"):
            uc.execute(DoThing(value=1))
        assert uc.seen_cid == "outer"

    def test_command_correlation_id_is_adopted(self):
        class Traced(Command):
            correlation_id: str | None = None

        class Echo(UseCase[Traced, str | None]):
            def execute(self, command: Traced) -> str | None:
                return get_correlation_id()

        assert Echo().execute(Traced(correlation_id="from-upstream")) == "from-upstream"
