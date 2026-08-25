"""A :class:`~domino.uow.unit_of_work.UnitOfWork` that manages a SQLAlchemy session."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from domino.events.publisher import EventPublisher
from domino.integrations.sqlalchemy.repository import (
    AsyncSqlAlchemyRepository,
    SqlAlchemyRepository,
)
from domino.uow.unit_of_work import AsyncUnitOfWork, UnitOfWork


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
            status = super().__exit__(exc_type, exc, tb)
        finally:
            if self._session is not None:
                self._session.close()
                self._session = None
                self._repositories = {}

        return status


class AsyncSqlAlchemyUnitOfWork(AsyncUnitOfWork):
    """An async unit of work that opens one :class:`AsyncSession` per scope.

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
    successful commit**: queue them during the scope with
    ``uow.enqueue_events(*aggregate.pull_pending_events())`` and they are
    dispatched once the transaction is durable (the classic "unit of work
    publishes domain events" pattern). A failing handler therefore can't roll the
    transaction back — and Domino's :class:`~domino.events.bus.EventBus` already
    isolates handler failures. The queue is cleared when the scope exits, and a
    rollback drops it.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        repositories: Mapping[str, type[AsyncSqlAlchemyRepository[Any]]],
        *,
        event_bus: EventPublisher | None = None,
    ) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._repository_types = dict(repositories)
        self._event_bus = event_bus
        self._session: AsyncSession | None = None
        self._repositories: dict[str, AsyncSqlAlchemyRepository[Any]] = {}
        self._committed = False

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
        return await super().__aenter__()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        try:
            status = await super().__aexit__(exc_type, exc, tb)
        finally:
            if self._session is not None:
                await self._session.close()
                self._session = None
                self._repositories = {}
                self._events = []

        return status

    async def commit(self) -> None:
        """Commit the transaction (idempotent within a scope)."""
        if self._committed:
            return
        await self.session.commit()
        if self._event_bus is not None:
            self._event_bus.publish(*self._events)
        self._committed = True

    async def rollback(self) -> None:
        """Roll back the transaction."""
        await self.session.rollback()
