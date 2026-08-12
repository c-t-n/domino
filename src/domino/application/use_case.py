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


class UseCase(ABC, Generic[C, R]):
    """Base class for application use cases.

    Usage::

        class PlaceOrder(UseCase[PlaceOrderCommand, OrderId]):
            def __init__(self, orders: OrderRepository, uow: UnitOfWork) -> None:
                self._orders = orders
                self._uow = uow

            def execute(self, command: PlaceOrderCommand) -> OrderId:
                with self._uow:
                    order = Order.create(command.customer_id)
                    self._orders.save(order)
                return order.id
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        execute = cls.__dict__.get("execute")
        if execute is not None and not getattr(execute, "__isabstractmethod__", False):
            # Transparently wrap the concrete execute so every call runs inside a
            # correlation scope; the wrapper preserves the original signature.
            cls.execute = _with_correlation(execute)  # ty: ignore[invalid-assignment]

    @abstractmethod
    def execute(self, command: C) -> R:
        """Run the use case for the given command and return its result."""
