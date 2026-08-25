"""FastAPI dependencies for the per-request unit of work."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from domino.uow.unit_of_work import AsyncUnitOfWork, UnitOfWork


def get_unit_of_work(request: Request) -> UnitOfWork | AsyncUnitOfWork:
    """Build a fresh unit of work for the current request.

    It calls the factory registered by
    :func:`~domino.integrations.fastapi.wiring.install_domino`, so each request
    gets its own instance — nothing is shared between concurrent requests.

    The unit of work is *constructed*, not entered: the transaction scope is
    opened by the route or the use case with ``async with uow:``.
    """
    return request.app.state.domino.unit_of_work_factory()


#: Annotated dependency: ``uow: UnitOfWorkDep`` in a route signature.
UnitOfWorkDep = Annotated[AsyncUnitOfWork, Depends(get_unit_of_work)]
