"""``AsyncFilterable`` — query an async repository with specifications."""

from __future__ import annotations

import builtins
from typing import Any, Generic, TypeVar

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from domino.core.entity import Entity
from domino.core.specification import Specification
from domino.integrations.sqlalchemy._loading import eager_load_options
from domino.integrations.sqlalchemy._specification_sql import to_clause

T = TypeVar("T", bound=Entity)


class AsyncFilterable(Generic[T]):
    """Mixin that adds ``await list(*specifications)`` to an async repository.

    The async counterpart of
    :class:`~domino.integrations.sqlalchemy.filtering.Filterable`. Mix it in
    alongside
    :class:`~domino.integrations.sqlalchemy.async_repository.AsyncSqlAlchemyRepository`::

        class OrderRepository(
            AsyncSqlAlchemyRepository[Order], AsyncFilterable[Order]
        ):
            ...

        await repo.list(eq("status", "confirmed"), in_("customer_id", [c1, c2]))
        await repo.list(gt("total", 100) | eq("vip", True))
        await repo.list()  # everything

    Positional specifications are AND-ed together; use ``&`` / ``|`` / ``~`` to
    build richer predicates. The same specifications also work in memory via
    :meth:`~domino.core.specification.Specification.is_satisfied_by`.
    """

    aggregate_type: type[T]
    _session: AsyncSession

    async def list(self, *specifications: Specification[Any]) -> builtins.list[T]:
        """Return every aggregate matching all the given specifications."""
        query = select(self.aggregate_type).options(
            *eager_load_options(self.aggregate_type)
        )
        if specifications:
            query = query.where(
                and_(*(to_clause(self.aggregate_type, s) for s in specifications))
            )
        result = await self._session.scalars(query)
        return list(result)
