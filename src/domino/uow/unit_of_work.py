"""Unit of Work — a transactional boundary around a set of operations.

The Unit of Work groups repositories and defines a single atomic scope: on a
clean exit it commits, on an exception it rolls back. It stays deliberately
thin — persistence is delegated to the ``commit``/``rollback`` hooks you inject
(e.g. a SQLAlchemy session's ``commit``/``rollback``). With an in-memory store
that writes on ``save``, the hooks default to no-ops.

Domain events raised during the scope are queued with ``enqueue_events`` and
published to the ``event_bus`` once the commit succeeds — never on a rollback.
The queue belongs to the scope: it is emptied when the scope exits, so the same
unit of work can be reused without replaying a previous scope's events.

Usage::

    uow = UnitOfWork({"orders": order_repo}, event_bus=bus,
                     commit=session.commit, rollback=session.rollback)

    with uow:
        order = uow.orders.get_by_id(order_id)
        order.confirm()
        uow.orders.save(order)
        uow.enqueue_events(*order.pull_pending_events())
        # commit happens automatically on a clean exit, then the events go out

:class:`AsyncUnitOfWork` is the ``async with`` twin, over
:class:`~domino.repository.repository.AsyncRepository` implementations.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from inspect import isawaitable
from typing import Any, Self

from domino.events.domain_event import DomainEvent
from domino.events.publisher import AsyncEventPublisher, EventPublisher
from domino.repository import AsyncRepository, Repository


class UnitOfWork:
    """A transactional scope that exposes repositories and commits atomically.

    Pass an ``event_bus`` to have the events queued with ``enqueue_events``
    published after a successful commit.
    """

    def __init__(
        self,
        repositories: Mapping[str, Repository[Any]] | None = None,
        *,
        event_bus: EventPublisher | None = None,
        commit: Callable[[], None] | None = None,
        rollback: Callable[[], None] | None = None,
    ) -> None:
        self._repositories: dict[str, Repository[Any]] = dict(repositories or {})
        self._commit_hook = commit
        self._rollback_hook = rollback
        self._committed = False
        self._event_bus = event_bus
        self._events = []

    def register(self, name: str, repository: Repository[Any]) -> None:
        """Add or replace a named repository."""
        self._repositories[name] = repository

    def repository(self, name: str) -> Repository[Any]:
        """Return a repository by name (``uow.repository("orders")``)."""
        try:
            return self._repositories[name]
        except KeyError:
            raise self._unknown_repository(name) from None

    def __getattr__(self, name: str):
        """Expose repositories as attributes (``uow.orders``)."""
        repositories = self.__dict__.get("_repositories", {})
        if name in repositories:
            return repositories[name]

        if name.startswith("_") and name in self.__dict__:
            return self.__dict__[name]

        raise self._unknown_repository(name)

    def _unknown_repository(self, name: str) -> AttributeError:
        available = sorted(self.__dict__.get("_repositories", {}))
        return AttributeError(
            f"UnitOfWork has no repository {name!r}. Available: {available}"
        )

    def __enter__(self) -> Self:
        self._committed = False
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._committed:
            self.commit()

        self._events = []
        return False

    def commit(self) -> None:
        """Commit the transaction (idempotent within a scope)."""
        if self._committed:
            return
        if self._commit_hook is not None:
            self._commit_hook()
        if self._event_bus is not None:
            self._event_bus.publish(*self._events)

        self._committed = True

    def rollback(self) -> None:
        """Roll back the transaction."""
        if self._rollback_hook is not None:
            self._rollback_hook()

    def enqueue_events(self, *events: DomainEvent):
        """Queue events for dispatch on commit.

        They are published to the ``event_bus`` once the commit succeeds, and
        dropped when the scope rolls back. The queue is cleared on exit.
        """
        self._events.extend(events)


class AsyncUnitOfWork:
    """An async transactional scope that exposes repositories and commits atomically.

    The ``async with`` counterpart of :class:`UnitOfWork`: same repository
    registry and same event queue, over
    :class:`~domino.repository.repository.AsyncRepository` implementations.
    """

    def __init__(
        self,
        repositories: Mapping[str, AsyncRepository[Any]] | None = None,
        *,
        event_bus: EventPublisher | AsyncEventPublisher | None = None,
        commit: Callable[[], None] | None = None,
        rollback: Callable[[], None] | None = None,
    ) -> None:
        self._repositories: dict[str, AsyncRepository[Any]] = dict(repositories or {})
        self._commit_hook = commit
        self._rollback_hook = rollback
        self._committed = False
        self._event_bus = event_bus
        self._events = []

    def register(self, name: str, repository: AsyncRepository[Any]) -> None:
        """Add or replace a named repository."""
        self._repositories[name] = repository

    def repository(self, name: str) -> AsyncRepository[Any]:
        """Return a repository by name (``uow.repository("orders")``)."""
        try:
            return self._repositories[name]
        except KeyError:
            raise self._unknown_repository(name) from None

    def __getattr__(self, name: str) -> Any:
        """Expose repositories as attributes (``uow.orders``)."""
        repositories = self.__dict__.get("_repositories", {})
        if name in repositories:
            return repositories[name]

        if name.startswith("_") and name in self.__dict__:
            return self.__dict__[name]

        raise self._unknown_repository(name)

    def _unknown_repository(self, name: str) -> AttributeError:
        available = sorted(self.__dict__.get("_repositories", {}))
        return AttributeError(
            f"UnitOfWork has no repository {name!r}. Available: {available}"
        )

    async def __aenter__(self) -> Self:
        self._committed = False
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is not None:
            await self.rollback()
        elif not self._committed:
            await self.commit()

        self._events = []
        return False

    async def commit(self) -> None:
        """Commit the transaction (idempotent within a scope)."""
        if self._committed:
            return
        if self._commit_hook is not None:
            self._commit_hook()
        await self._publish_events()

        self._committed = True

    async def rollback(self) -> None:
        """Roll back the transaction."""
        if self._rollback_hook is not None:
            self._rollback_hook()

    def enqueue_events(self, *events: DomainEvent):
        """Queue events for dispatch on commit.

        They are published to the ``event_bus`` once the commit succeeds, and
        dropped when the scope rolls back. The queue is cleared on exit.
        """
        self._events.extend(events)

    async def _publish_events(self) -> None:
        """Hand the queued events to the bus, awaiting an asynchronous one.

        Dispatching on the returned value rather than on the bus type lets an
        async unit of work drive a synchronous
        :class:`~domino.events.bus.EventBus` — the in-memory one, typically in
        tests — as well as an async broker client.
        """
        if self._event_bus is None:
            return
        result = self._event_bus.publish(*self._events)
        if isawaitable(result):
            await result
