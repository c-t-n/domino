"""An async unit of work managing a SQLAlchemy :class:`AsyncSession`."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from domino.sqlalchemy.async_repository import AsyncSqlAlchemyRepository


class AsyncSqlAlchemyUnitOfWork:
    """A unit of work that opens one :class:`AsyncSession` per scope.

    The async counterpart of
    :class:`~domino.sqlalchemy.unit_of_work.SqlAlchemyUnitOfWork`, driven with
    ``async with``. Give it a session factory (an ``async_sessionmaker`` or any
    zero-arg callable returning an :class:`AsyncSession`) and a mapping of name to
    repository *class*::

        uow = AsyncSqlAlchemyUnitOfWork(session_factory, {"orders": OrderRepository})

        async with uow:
            order = await uow.orders.get_by_id(order_id)
            order.confirm()
            await uow.orders.save(order)
            # commit on clean exit, rollback on exception, session always closed

    The same instance is reusable: each ``async with`` block gets a fresh session,
    available as ``uow.session`` inside the block.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        repositories: Mapping[str, type[AsyncSqlAlchemyRepository[Any]]],
    ) -> None:
        self._session_factory = session_factory
        self._repository_types = dict(repositories)
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

    async def rollback(self) -> None:
        """Roll back the transaction."""
        if self._session is not None:
            await self._session.rollback()
