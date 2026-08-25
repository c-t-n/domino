"""Tests for the transactional outbox and its relay."""

from __future__ import annotations

from dataclasses import field
from datetime import datetime

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import Column, MetaData, String, Table, create_engine, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import registry as orm_registry
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from domino import (
    AggregateRoot,
    AsyncEventPublisher,
    DomainEvent,
    DomainId,
    EventPublisher,
    EventRegistry,
)
from domino.integrations.sqlalchemy import (
    AsyncOutboxRelay,
    AsyncSqlAlchemyRepository,
    AsyncSqlAlchemyUnitOfWork,
    DomainIdType,
    Outbox,
    OutboxRelay,
    SqlAlchemyRepository,
    SqlAlchemyUnitOfWork,
)

# --- Domain -----------------------------------------------------------------


class NoteWritten(DomainEvent):
    note_id: DomainId
    title: str


class Note(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    title: str = ""

    def write(self) -> None:
        self._add_event(NoteWritten(note_id=self._id, title=self.title))


metadata = MetaData()
mapper_registry = orm_registry()

notes_table = Table(
    "notes",
    metadata,
    Column("id", DomainIdType, primary_key=True, key="_id"),
    Column("title", String(100), nullable=False),
)
mapper_registry.map_imperatively(Note, notes_table)

event_registry = EventRegistry()
event_registry.register(NoteWritten)

# The outbox table joins the same metadata, so create_all() builds it too.
outbox = Outbox(event_registry, metadata=metadata)


class NoteRepository(SqlAlchemyRepository[Note]):
    pass


class AsyncNoteRepository(AsyncSqlAlchemyRepository[Note]):
    pass


# --- Test doubles -----------------------------------------------------------


class RecordingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    def publish(self, *events: DomainEvent) -> None:
        self.published.extend(events)


class RecordingAsyncPublisher(AsyncEventPublisher):
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    async def publish(self, *events: DomainEvent) -> None:
        self.published.extend(events)


class FlakyPublisher(EventPublisher):
    """Fails on the nth event it is handed (1-based)."""

    def __init__(self, fail_on: int) -> None:
        self.published: list[DomainEvent] = []
        self._fail_on = fail_on
        self._seen = 0

    def publish(self, *events: DomainEvent) -> None:
        for event in events:
            self._seen += 1
            if self._seen == self._fail_on:
                raise RuntimeError("broker unreachable")
            self.published.append(event)


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


def _titles(events: list[DomainEvent]) -> list[str]:
    """Titles of the NoteWritten events, in order."""
    return [e.title for e in events if isinstance(e, NoteWritten)]


def _note(title: str = "a note") -> Note:
    note = Note(title=title)
    note.write()
    return note


def _lines(session_factory) -> list:
    with session_factory() as session:
        return session.execute(select(outbox.table).order_by(outbox.table.c.id)).all()


async def _lines_async(session_factory) -> list:
    async with session_factory() as session:
        result = await session.execute(select(outbox.table).order_by(outbox.table.c.id))
        return result.all()


# --- Tests ------------------------------------------------------------------


class TestStaging:
    def test_events_are_written_in_the_transaction(self, session_factory):
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, outbox=outbox
        )

        with uow:
            note = _note()
            uow.notes.save(note)
            uow.enqueue_events(*note.pull_pending_events())

        (line,) = _lines(session_factory)
        assert line.event_name == "NoteWritten"
        assert line.published_at is None
        assert line.attempts == 0
        assert isinstance(line.occurred_on, datetime)

    def test_a_rollback_takes_the_outbox_lines_with_it(self, session_factory):
        # The whole point: no event survives a transaction that never happened.
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, outbox=outbox
        )

        with pytest.raises(ValueError), uow:
            note = _note()
            uow.notes.save(note)
            uow.enqueue_events(*note.pull_pending_events())
            raise ValueError("boom")

        assert _lines(session_factory) == []
        with session_factory() as session:
            assert session.execute(select(notes_table)).all() == []

    def test_rows_and_events_commit_together(self, session_factory):
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, outbox=outbox
        )

        with uow:
            note = _note("saved")
            uow.notes.save(note)
            uow.enqueue_events(*note.pull_pending_events())

        with session_factory() as session:
            assert len(session.execute(select(notes_table)).all()) == 1
        assert len(_lines(session_factory)) == 1

    def test_no_events_no_lines(self, session_factory):
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, outbox=outbox
        )

        with uow:
            uow.notes.save(Note(title="quiet"))

        assert _lines(session_factory) == []

    async def test_async_staging(self, async_session_factory):
        uow = AsyncSqlAlchemyUnitOfWork(
            async_session_factory, {"notes": AsyncNoteRepository}, outbox=outbox
        )

        async with uow:
            note = _note("async note")
            await uow.notes.save(note)
            uow.enqueue_events(*note.pull_pending_events())

        (line,) = await _lines_async(async_session_factory)
        assert line.event_name == "NoteWritten"
        assert line.published_at is None


class TestRelay:
    def test_publishes_and_marks_the_lines(self, session_factory):
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, outbox=outbox
        )
        with uow:
            note = _note("relayed")
            uow.notes.save(note)
            uow.enqueue_events(*note.pull_pending_events())

        publisher = RecordingPublisher()
        relay = OutboxRelay(session_factory, outbox, publisher=publisher)

        assert relay.run_once() == 1
        assert isinstance(publisher.published[0], NoteWritten)
        assert publisher.published[0].title == "relayed"
        (line,) = _lines(session_factory)
        assert line.published_at is not None

    def test_the_event_round_trips_through_the_table(self, session_factory):
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, outbox=outbox
        )
        with uow:
            note = _note("exact")
            uow.notes.save(note)
            original = note.pull_pending_events()
            uow.enqueue_events(*original)

        publisher = RecordingPublisher()
        OutboxRelay(session_factory, outbox, publisher=publisher).run_once()

        assert publisher.published == original  # same id, timestamp, payload

    def test_a_published_line_is_not_sent_again(self, session_factory):
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, outbox=outbox
        )
        with uow:
            note = _note()
            uow.notes.save(note)
            uow.enqueue_events(*note.pull_pending_events())

        publisher = RecordingPublisher()
        relay = OutboxRelay(session_factory, outbox, publisher=publisher)

        assert relay.run_once() == 1
        assert relay.run_once() == 0  # nothing left
        assert len(publisher.published) == 1

    def test_empty_outbox_is_a_noop(self, session_factory):
        relay = OutboxRelay(session_factory, outbox, publisher=RecordingPublisher())
        assert relay.run_once() == 0

    def test_order_is_preserved(self, session_factory):
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, outbox=outbox
        )
        for title in ("first", "second", "third"):
            with uow:
                note = _note(title)
                uow.notes.save(note)
                uow.enqueue_events(*note.pull_pending_events())

        publisher = RecordingPublisher()
        OutboxRelay(session_factory, outbox, publisher=publisher).run_once()

        assert _titles(publisher.published) == ["first", "second", "third"]

    def test_batch_size_limits_a_pass(self, session_factory):
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, outbox=outbox
        )
        for title in ("a", "b", "c"):
            with uow:
                note = _note(title)
                uow.notes.save(note)
                uow.enqueue_events(*note.pull_pending_events())

        relay = OutboxRelay(
            session_factory, outbox, publisher=RecordingPublisher(), batch_size=2
        )
        assert relay.run_once() == 2
        assert relay.run_once() == 1
        assert relay.run_once() == 0

    def test_a_failure_stops_the_batch_and_keeps_the_line(
        self, session_factory, caplog
    ):
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, outbox=outbox
        )
        for title in ("ok", "fails", "later"):
            with uow:
                note = _note(title)
                uow.notes.save(note)
                uow.enqueue_events(*note.pull_pending_events())

        publisher = FlakyPublisher(fail_on=2)
        relay = OutboxRelay(session_factory, outbox, publisher=publisher)

        assert relay.run_once() == 1  # only the first went out
        lines = _lines(session_factory)
        assert lines[0].published_at is not None
        assert lines[1].published_at is None  # kept for the next pass
        assert lines[1].attempts == 1
        assert "broker unreachable" in (lines[1].last_error or "")
        assert lines[2].published_at is None  # order preserved: not skipped ahead

    def test_a_recovered_broker_resumes_where_it_stopped(self, session_factory):
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, outbox=outbox
        )
        for title in ("ok", "fails"):
            with uow:
                note = _note(title)
                uow.notes.save(note)
                uow.enqueue_events(*note.pull_pending_events())

        OutboxRelay(
            session_factory, outbox, publisher=FlakyPublisher(fail_on=2)
        ).run_once()

        healthy = RecordingPublisher()
        assert OutboxRelay(session_factory, outbox, publisher=healthy).run_once() == 1
        assert _titles(healthy.published) == ["fails"]


class TestAsyncRelay:
    async def test_publishes_and_marks_the_lines(self, async_session_factory):
        uow = AsyncSqlAlchemyUnitOfWork(
            async_session_factory, {"notes": AsyncNoteRepository}, outbox=outbox
        )
        async with uow:
            note = _note("async")
            await uow.notes.save(note)
            uow.enqueue_events(*note.pull_pending_events())

        publisher = RecordingAsyncPublisher()
        relay = AsyncOutboxRelay(async_session_factory, outbox, publisher=publisher)

        assert await relay.run_once() == 1
        assert _titles(publisher.published) == ["async"]
        assert await relay.run_once() == 0

    async def test_accepts_a_sync_publisher(self, async_session_factory):
        uow = AsyncSqlAlchemyUnitOfWork(
            async_session_factory, {"notes": AsyncNoteRepository}, outbox=outbox
        )
        async with uow:
            note = _note()
            await uow.notes.save(note)
            uow.enqueue_events(*note.pull_pending_events())

        publisher = RecordingPublisher()
        relay = AsyncOutboxRelay(async_session_factory, outbox, publisher=publisher)
        assert await relay.run_once() == 1

    async def test_a_rollback_leaves_nothing_behind(self, async_session_factory):
        uow = AsyncSqlAlchemyUnitOfWork(
            async_session_factory, {"notes": AsyncNoteRepository}, outbox=outbox
        )
        with pytest.raises(ValueError):
            async with uow:
                note = _note()
                await uow.notes.save(note)
                uow.enqueue_events(*note.pull_pending_events())
                raise ValueError("boom")

        relay = AsyncOutboxRelay(
            async_session_factory, outbox, publisher=RecordingAsyncPublisher()
        )
        assert await relay.run_once() == 0


class TestConfiguration:
    def test_table_or_metadata_is_required(self):
        with pytest.raises(ValueError, match="metadata"):
            Outbox(event_registry)

    def test_a_custom_table_name(self):
        other = Outbox(event_registry, metadata=MetaData(), name="events_outbox")
        assert other.table.name == "events_outbox"

    def test_in_process_handlers_and_the_outbox_coexist(self, session_factory):
        # event_bus feeds local handlers after commit; the outbox feeds the
        # broker. Wanting both is the normal case, not an edge case.
        bus = RecordingPublisher()
        uow = SqlAlchemyUnitOfWork(
            session_factory, {"notes": NoteRepository}, event_bus=bus, outbox=outbox
        )

        with uow:
            note = _note("both")
            uow.notes.save(note)
            uow.enqueue_events(*note.pull_pending_events())

        assert len(bus.published) == 1
        assert len(_lines(session_factory)) == 1
