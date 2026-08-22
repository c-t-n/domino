"""A :class:`~domino.uow.unit_of_work.UnitOfWork` that manages a SQLAlchemy session."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from domino.aggregate.aggregate_root import AggregateRoot
from domino.events.domain_event import DomainEvent
from domino.events.publisher import EventPublisher
from domino.integrations.sqlalchemy.repository import (
    AsyncSqlAlchemyRepository,
    SqlAlchemyRepository,
)
from domino.uow.unit_of_work import UnitOfWork


class SqlAlchemyUnitOfWork(UnitOfWork):
    """A unit of work that opens one SQLAlchemy session per scope.

    Give it a session factory (a ``sessionmaker`` or any zero-arg callable
    returning a :class:`Session`) and a mapping of name to repository *class*.
    Entering the ``with`` block opens a session, builds the repositories bound to
    it, and drives the session's commit/rollback; leaving it closes the session::

        uow = SqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository})

        with uow:
            order = uow.orders.get_by_id(order_id)
            order.confirm()
            uow.orders.save(order)
            # commit on clean exit, rollback on exception, session always closed

    The same instance is reusable: each ``with`` block gets a fresh session. The
    live session is available as ``uow.session`` inside the block.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        repositories: Mapping[str, type[SqlAlchemyRepository[Any]]],
    ) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._repository_types = dict(repositories)
        self._session: Session | None = None

    @property
    def session(self) -> Session:
        """The session for the current scope (only valid inside a ``with`` block)."""
        if self._session is None:
            raise RuntimeError("the session is only available inside a `with` block")
        return self._session

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        session = self._session_factory()
        self._session = session
        self._repositories = {
            name: repo_type(session)
            for name, repo_type in self._repository_types.items()
        }
        self._commit_hook = session.commit
        self._rollback_hook = session.rollback
        super().__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            if self._session is not None:
                self._session.close()
                self._session = None
                self._repositories = {}


class AsyncSqlAlchemyUnitOfWork:
    """A unit of work that opens one :class:`AsyncSession` per scope.

    The async counterpart of the
    :class:`~domino.integrations.sqlalchemy.unit_of_work.SqlAlchemyUnitOfWork`,
    driven with ``async with``. Give it a session factory (an
    ``async_sessionmaker`` or any zero-arg callable returning an
    :class:`AsyncSession`) and a mapping of name to repository *class*::

        uow = AsyncSqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository})

        async with uow:
            order = await uow.orders.get_by_id(order_id)
            order.confirm()
            await uow.orders.save(order)
            # commit on clean exit, rollback on exception, session always closed

    The same instance is reusable: each ``async with`` block gets a fresh session,
    available as ``uow.session`` inside the block.

    Pass an ``event_bus`` to have the unit of work publish domain events **after a
    successful commit**: it scans the session for aggregates with pending events
    and dispatches them (the classic "unit of work publishes domain events"
    pattern). Handlers run once the transaction is durable, so a failing handler
    can't roll it back — Domino's :class:`~domino.events.bus.EventBus` already
    isolates handler failures.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        repositories: Mapping[str, type[AsyncSqlAlchemyRepository[Any]]],
        *,
        event_bus: EventPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._repository_types = dict(repositories)
        self._event_bus = event_bus
        self._session: AsyncSession | None = None
        self._repositories: dict[str, AsyncSqlAlchemyRepository[Any]] = {}
        self._committed = False

    def register(self, name: str, repository: AsyncSqlAlchemyRepository[Any]) -> None:
        """Add or replace a named repository."""
        self._repositories[name] = repository

    def repository(self, name: str) -> AsyncSqlAlchemyRepository[Any]:
        """Return a repository by name (``uow.repository("orders")``)."""
        try:
            return self._repositories[name]
        except KeyError:
            raise self._unknown_repository(name) from None

    def __getattr__(self, name: str) -> Any:
        """Expose repositories as attributes (``uow.orders``)."""
        if name.startswith("_"):
            raise AttributeError(name)
        repositories = self.__dict__.get("_repositories", {})
        if name in repositories:
            return repositories[name]
        raise self._unknown_repository(name)

    def _unknown_repository(self, name: str) -> AttributeError:
        available = sorted(self.__dict__.get("_repositories", {}))
        return AttributeError(
            f"AsyncSqlAlchemyUnitOfWork has no repository {name!r}. "
            f"Available: {available}"
        )

    @property
    def session(self) -> AsyncSession:
        """The session for the current scope (valid only inside ``async with``)."""
        if self._session is None:
            raise RuntimeError(
                "the session is only available inside an `async with` block"
            )
        return self._session

    async def __aenter__(self) -> AsyncSqlAlchemyUnitOfWork:
        session = self._session_factory()
        self._session = session
        self._repositories = {
            name: repo_type(session)
            for name, repo_type in self._repository_types.items()
        }
        self._committed = False
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        try:
            if exc_type is not None:
                await self.rollback()
            elif not self._committed:
                await self.commit()
        finally:
            if self._session is not None:
                await self._session.close()
                self._session = None
                self._repositories = {}
        return False

    async def commit(self) -> None:
        """Commit the transaction (idempotent within a scope)."""
        if self._committed:
            return
        await self.session.commit()
        self._committed = True
        if self._event_bus is not None:
            self._publish_events()

    async def rollback(self) -> None:
        """Roll back the transaction."""
        if self._session is not None:
            await self._session.rollback()

    def _publish_events(self) -> None:
        # After commit the session still holds every aggregate it loaded or
        # persisted; collect the events they raised this scope and publish once.
        events: list[DomainEvent] = []
        for obj in list(self.session.identity_map.values()):
            if isinstance(obj, AggregateRoot) and obj.has_pending_events():
                events.extend(obj.pull_pending_events())
        if events and self._event_bus is not None:
            self._event_bus.publish(*events)
