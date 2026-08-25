"""UseCase — an application service that orchestrates one user goal.

A use case is the entry point from the presentation layer (HTTP, CLI). It stays
thin: it validates input, drives the domain layer, manages the transaction
boundary, and returns a result to the caller — it holds no business logic of its
own. It is generic over its command (a :class:`~domino.application.command.Command`
input) and result (output) types.

Every ``execute`` call automatically runs inside a
:func:`~domino.core.correlation.correlation_scope`, so a correlation id is
generated once per call and captured by every domain event produced along the
way — you never thread it through your code. A nested use case reuses the
caller's id, and if the command carries a ``correlation_id`` that trace is
continued instead of starting a new one.
"""

from __future__ import annotations

import functools
from abc import ABC, abstractmethod
from collections.abc import Callable
from inspect import iscoroutinefunction
from typing import Any, Generic, TypeVar

from domino.application.command import Command
from domino.core.correlation import correlation_scope, get_correlation_id
from domino.core.logging import LoggerMixin
from domino.uow.unit_of_work import AsyncUnitOfWork, UnitOfWork

C = TypeVar("C", bound=Command)
R = TypeVar("R")


def _with_correlation(execute: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``execute`` so it runs inside a correlation scope (sync or async)."""
    if iscoroutinefunction(execute):

        @functools.wraps(execute)
        async def async_run(self: Any, command: Any) -> Any:
            if get_correlation_id() is not None:
                return await execute(self, command)
            with correlation_scope(getattr(command, "correlation_id", None)):
                return await execute(self, command)

        return async_run

    @functools.wraps(execute)
    def run(self: Any, command: Any) -> Any:
        if get_correlation_id() is not None:
            return execute(self, command)
        with correlation_scope(getattr(command, "correlation_id", None)):
            return execute(self, command)

    return run


class UseCase(LoggerMixin, ABC, Generic[C, R]):
    """Base class for application use cases.

    The constructor takes the :class:`~domino.uow.unit_of_work.UnitOfWork` and
    exposes it as ``self._uow``, so repositories are reached through it::

        class PlaceOrder(UseCase[PlaceOrderCommand, OrderId]):
            def execute(self, command: PlaceOrderCommand) -> OrderId:
                order = Order.create(command.customer_id)
                self._uow.orders.save(order)
                self._uow.enqueue_events(*order.pull_pending_events())
                return order.id

    The transaction scope is a ``with`` block on that unit of work. Open it
    inside ``execute`` when the use case owns the transaction, or let the caller
    own it::

        with uow:
            order_id = PlaceOrder(uow).execute(command)
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        execute = cls.__dict__.get("execute")
        if execute is not None and not getattr(execute, "__isabstractmethod__", False):
            # Transparently wrap the concrete execute so every call runs inside a
            # correlation scope; the wrapper preserves the original signature.
            cls.execute = _with_correlation(execute)  # ty: ignore[invalid-assignment]

    def __init__(self, uow: UnitOfWork):
        self._uow = uow

    @abstractmethod
    def execute(self, command: C) -> R:
        """Run the use case for the given command and return its result."""


class AsyncUseCase(LoggerMixin, ABC, Generic[C, R]):
    """Base class for asynchronous use cases (``async def execute``).

    Identical to :class:`UseCase` but for ``async`` application services — the
    natural fit for an async presentation layer (FastAPI) and the async SQLAlchemy
    unit of work. It takes an
    :class:`~domino.uow.unit_of_work.AsyncUnitOfWork`, and ``execute`` is still
    wrapped in a correlation scope, reusing an upstream one (e.g. opened by a web
    middleware) when present::

        class PlaceOrder(AsyncUseCase[PlaceOrderCommand, OrderId]):
            async def execute(self, command: PlaceOrderCommand) -> OrderId:
                order = Order.create(command.customer_id)
                await self._uow.orders.save(order)
                self._uow.enqueue_events(*order.pull_pending_events())
                return order.id

        async with uow:
            order_id = await PlaceOrder(uow).execute(command)
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        execute = cls.__dict__.get("execute")
        if execute is not None and not getattr(execute, "__isabstractmethod__", False):
            cls.execute = _with_correlation(execute)  # ty: ignore[invalid-assignment]

    def __init__(self, uow: AsyncUnitOfWork):
        self._uow = uow

    @abstractmethod
    async def execute(self, command: C) -> R:
        """Run the use case for the given command and return its result."""
