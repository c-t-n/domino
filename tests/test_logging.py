"""Tests for context-aware logging (get_logger and self.log)."""

from __future__ import annotations

import logging
from dataclasses import field

import pytest

from domino import (
    AggregateRoot,
    Command,
    DomainEvent,
    DomainId,
    EventHandler,
    UseCase,
    correlation_scope,
    get_logger,
)
from domino.uow import UnitOfWork


class TestGetLogger:
    def test_is_cached_per_context(self):
        assert get_logger("A") is get_logger("A")
        assert get_logger("A") is not get_logger("B")

    def test_prefixes_context_and_correlation_id(
        self, caplog: pytest.LogCaptureFixture
    ):
        with (
            correlation_scope("cid-123"),
            caplog.at_level(logging.INFO, logger="domino"),
        ):
            get_logger("Widget").info("hello %s", "world")

        record = caplog.records[-1]
        assert record.getMessage() == "[Widget] [cid=cid-123] hello world"
        # correlation_id / domino_context are attached to the record via `extra`.
        assert record.__dict__["correlation_id"] == "cid-123"
        assert record.__dict__["domino_context"] == "Widget"

    def test_no_correlation_prefix_without_scope(
        self, caplog: pytest.LogCaptureFixture
    ):
        with caplog.at_level(logging.INFO, logger="domino"):
            get_logger("Widget").info("hi")

        record = caplog.records[-1]
        assert record.getMessage() == "[Widget] hi"
        assert record.__dict__["correlation_id"] is None


class TestSelfLog:
    def test_context_matches_owning_class(self):
        uow = UnitOfWork()

        class Thing(AggregateRoot):
            _id: DomainId = field(default_factory=DomainId.generate)

        class DoThing(Command):
            pass

        class Act(UseCase[DoThing, None]):
            def execute(self, command: DoThing) -> None: ...

        class OnEvent(EventHandler):
            def handle(self, event: DomainEvent) -> None: ...

        assert Thing().log.context == "Thing"
        assert Act(uow).log.context == "Act"
        assert OnEvent().log.context == "OnEvent"

    def test_use_case_log_carries_the_correlation_id(
        self, caplog: pytest.LogCaptureFixture
    ):
        uow = UnitOfWork()

        class DoThing(Command):
            pass

        class Act(UseCase[DoThing, None]):
            def execute(self, command: DoThing) -> None:
                self.log.info("working")

        with caplog.at_level(logging.INFO, logger="domino"):
            Act(uow).execute(DoThing())

        record = next(
            r for r in caplog.records if r.__dict__.get("domino_context") == "Act"
        )
        assert record.__dict__["correlation_id"] is not None  # scope was opened
        assert "[cid=" in record.getMessage()
