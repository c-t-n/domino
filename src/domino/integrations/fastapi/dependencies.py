"""FastAPI dependencies for the per-request unit of work."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from domino.integrations.fastapi.state import DominoState
from domino.integrations.sqlalchemy.async_unit_of_work import AsyncSqlAlchemyUnitOfWork


def get_unit_of_work(request: Request) -> AsyncSqlAlchemyUnitOfWork:
    """Instantiate a fresh unit of work for the current request.

    It is *constructed*, not entered: the use case owns the transaction and opens
    ``async with uow:`` when it runs. The session factory, repositories and event
    bus come from ``app.state.domino`` (see
    :func:`~domino.integrations.fastapi.wiring.install_domino`).
    """
    state: DominoState = request.app.state.domino
    return AsyncSqlAlchemyUnitOfWork(
        state.session_factory, state.repositories, event_bus=state.event_bus
    )


#: Annotated dependency: ``uow: UnitOfWorkDep`` in a route signature.
UnitOfWorkDep = Annotated[AsyncSqlAlchemyUnitOfWork, Depends(get_unit_of_work)]
