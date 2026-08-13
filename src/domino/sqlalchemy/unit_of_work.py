"""A :class:`~domino.uow.unit_of_work.UnitOfWork` that manages a SQLAlchemy session."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy.orm import Session

from domino.sqlalchemy.repository import SqlAlchemyRepository
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
