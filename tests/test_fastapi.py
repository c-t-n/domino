"""Tests for the optional FastAPI integration (domino.fastapi)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import field
from typing import Annotated

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import httpx
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import Boolean, Column, MetaData, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import registry
from sqlalchemy.pool import StaticPool

from domino import (
    AggregateRoot,
    AsyncUseCase,
    Command,
    DomainEvent,
    DomainId,
    DomainNotFoundError,
    DomainStateError,
)
from domino.events import EventBus, EventHandler
from domino.fastapi import UnitOfWorkDep, install_domino, query_filter
from domino.sqlalchemy import (
    AsyncFilterable,
    AsyncSqlAlchemyRepository,
    AsyncSqlAlchemyUnitOfWork,
    DomainIdType,
)

# --- Domain (pure Domino) ---------------------------------------------------


class NoteArchived(DomainEvent):
    note_id: DomainId


class Note(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    title: str = ""
    archived: bool = False

    def archive(self) -> None:
        if self.archived:
            raise DomainStateError("note already archived")
        self.archived = True
        self._add_event(NoteArchived(note_id=self._id))


# --- Infrastructure: tables + imperative mapping (own registry) -------------

metadata = MetaData()
mapper_registry = registry()

notes_table = Table(
    "notes",
    metadata,
    Column("id", DomainIdType, primary_key=True),
    Column("title", String(200), nullable=False),
    Column("archived", Boolean, nullable=False),
)
mapper_registry.map_imperatively(
    Note, notes_table, properties={"_id": notes_table.c.id}
)


class NoteRepository(AsyncSqlAlchemyRepository[Note], AsyncFilterable[Note]):
    pass


# --- Application: commands + use cases --------------------------------------


class CreateNoteCommand(Command):
    title: str


class CreateNote(AsyncUseCase[CreateNoteCommand, DomainId]):
    def __init__(self, uow: AsyncSqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: CreateNoteCommand) -> DomainId:
        async with self._uow:
            note = Note(title=command.title)
            await self._uow.notes.save(note)
        return note.id


class ArchiveNoteCommand(Command):
    note_id: DomainId


class ArchiveNote(AsyncUseCase[ArchiveNoteCommand, None]):
    def __init__(self, uow: AsyncSqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: ArchiveNoteCommand) -> None:
        async with self._uow:
            note = await self._uow.notes.get_by_id(command.note_id)
            if note is None:
                raise DomainNotFoundError(f"note {command.note_id} not found")
            note.archive()
            await self._uow.notes.save(note)


# --- Presentation: the FastAPI app ------------------------------------------


class CreateNoteBody(BaseModel):
    title: str


def _parse_bool(raw: str) -> bool:
    return raw.lower() in {"1", "true", "yes", "on"}


# Module-level so FastAPI can resolve it from globals under `from __future__
# import annotations` (a function-local alias would not resolve).
NoteFilters = Annotated[list, Depends(query_filter({"archived": _parse_bool}))]


def build_app() -> FastAPI:
    app = FastAPI()

    @app.post("/notes", status_code=201)
    async def create_note(body: CreateNoteBody, uow: UnitOfWorkDep) -> dict[str, str]:
        note_id = await CreateNote(uow).execute(CreateNoteCommand(title=body.title))
        return {"id": str(note_id)}

    @app.get("/notes/{note_id}")
    async def get_note(note_id: str, uow: UnitOfWorkDep) -> dict[str, object]:
        async with uow:
            note = await uow.notes.get_by_id(DomainId(note_id))
            if note is None:
                raise DomainNotFoundError(f"note {note_id} not found")
            return {"id": str(note.id), "title": note.title, "archived": note.archived}

    @app.post("/notes/{note_id}/archive", status_code=204)
    async def archive_note(note_id: str, uow: UnitOfWorkDep) -> None:
        await ArchiveNote(uow).execute(ArchiveNoteCommand(note_id=DomainId(note_id)))

    @app.get("/notes")
    async def list_notes(
        uow: UnitOfWorkDep, specs: NoteFilters
    ) -> list[dict[str, object]]:
        async with uow:
            notes = await uow.notes.list(*specs)
            return [
                {"id": str(n.id), "title": n.title, "archived": n.archived}
                for n in notes
            ]

    return app


class _Recorder(EventHandler):
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def handle(self, event: DomainEvent) -> None:
        self.events.append(event)


@pytest.fixture
async def client_and_recorder() -> AsyncIterator[tuple[httpx.AsyncClient, _Recorder]]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    recorder = _Recorder()
    bus = EventBus()
    bus.register(NoteArchived, recorder)

    app = build_app()
    install_domino(
        app,
        session_factory=session_factory,
        repositories={"notes": NoteRepository},
        event_bus=bus,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, recorder
    await engine.dispose()


class TestRoutesAndUnitOfWork:
    async def test_create_and_get(self, client_and_recorder):
        client, _ = client_and_recorder
        created = await client.post("/notes", json={"title": "buy milk"})
        assert created.status_code == 201
        note_id = created.json()["id"]

        fetched = await client.get(f"/notes/{note_id}")
        assert fetched.status_code == 200
        assert fetched.json() == {"id": note_id, "title": "buy milk", "archived": False}

    async def test_not_found_maps_to_404(self, client_and_recorder):
        client, _ = client_and_recorder
        missing = str(DomainId.generate())
        response = await client.get(f"/notes/{missing}")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"

    async def test_state_error_maps_to_409(self, client_and_recorder):
        client, _ = client_and_recorder
        note_id = (await client.post("/notes", json={"title": "x"})).json()["id"]
        assert (await client.post(f"/notes/{note_id}/archive")).status_code == 204
        conflict = await client.post(f"/notes/{note_id}/archive")
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "STATE_ERROR"


class TestCorrelation:
    async def test_echoes_incoming_header(self, client_and_recorder):
        client, _ = client_and_recorder
        note_id = (await client.post("/notes", json={"title": "x"})).json()["id"]
        response = await client.post(
            f"/notes/{note_id}/archive", headers={"X-Request-ID": "trace-abc"}
        )
        assert response.status_code == 204
        assert response.headers["X-Request-ID"] == "trace-abc"

    async def test_generates_one_when_absent(self, client_and_recorder):
        client, _ = client_and_recorder
        response = await client.post("/notes", json={"title": "x"})
        assert response.headers.get("X-Request-ID")


class TestEventDispatch:
    async def test_events_published_after_commit(self, client_and_recorder):
        client, recorder = client_and_recorder
        note_id = (await client.post("/notes", json={"title": "x"})).json()["id"]
        await client.post(
            f"/notes/{note_id}/archive", headers={"X-Request-ID": "trace-xyz"}
        )
        assert len(recorder.events) == 1
        event = recorder.events[0]
        assert isinstance(event, NoteArchived)
        # the event carries the request's correlation id
        assert event.correlation_id == "trace-xyz"

    async def test_no_events_on_rollback(self, client_and_recorder):
        client, recorder = client_and_recorder
        missing = str(DomainId.generate())
        await client.post(f"/notes/{missing}/archive")  # 404, rolled back
        assert recorder.events == []


class TestQueryFilter:
    async def test_filters_by_query_param(self, client_and_recorder):
        client, _ = client_and_recorder
        first = (await client.post("/notes", json={"title": "a"})).json()["id"]
        await client.post("/notes", json={"title": "b"})
        await client.post(f"/notes/{first}/archive")

        archived = await client.get("/notes", params={"archived": "true"})
        assert archived.status_code == 200
        assert [n["id"] for n in archived.json()] == [first]

        active = await client.get("/notes", params={"archived": "false"})
        assert len(active.json()) == 1

    async def test_no_filter_lists_all(self, client_and_recorder):
        client, _ = client_and_recorder
        await client.post("/notes", json={"title": "a"})
        await client.post("/notes", json={"title": "b"})
        assert len((await client.get("/notes")).json()) == 2
