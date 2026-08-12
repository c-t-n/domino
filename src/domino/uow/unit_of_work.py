"""Unit of Work — a transactional boundary around a set of operations.

The Unit of Work groups repositories and defines a single atomic scope: on a
clean exit it commits, on an exception it rolls back. It stays deliberately
thin — persistence is delegated to the ``commit``/``rollback`` hooks you inject
(e.g. a SQLAlchemy session's ``commit``/``rollback``). With an in-memory store
that writes on ``save``, the hooks default to no-ops.

Usage::

    uow = UnitOfWork({"orders": order_repo}, commit=session.commit,
                     rollback=session.rollback)

    with uow:
        order = uow.orders.get_by_id(order_id)
        order.confirm()
        uow.orders.save(order)
        # commit happens automatically on a clean exit
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from domino.repository.repository import Repository


class UnitOfWork:
    """A transactional scope that exposes repositories and commits atomically."""

    def __init__(
        self,
        repositories: Mapping[str, Repository[Any]] | None = None,
        *,
        commit: Callable[[], None] | None = None,
        rollback: Callable[[], None] | None = None,
    ) -> None:
        self._repositories: dict[str, Repository[Any]] = dict(repositories or {})
        self._commit_hook = commit
        self._rollback_hook = rollback
        self._committed = False

    def register(self, name: str, repository: Repository[Any]) -> None:
        """Add or replace a named repository."""
        self._repositories[name] = repository

    def repository(self, name: str) -> Repository[Any]:
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
            f"UnitOfWork has no repository {name!r}. Available: {available}"
        )

    def __enter__(self) -> UnitOfWork:
        self._committed = False
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._committed:
            self.commit()
        return False

    def commit(self) -> None:
        """Commit the transaction (idempotent within a scope)."""
        if self._committed:
            return
        if self._commit_hook is not None:
            self._commit_hook()
        self._committed = True

    def rollback(self) -> None:
        """Roll back the transaction."""
        if self._rollback_hook is not None:
            self._rollback_hook()
