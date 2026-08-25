"""The Domino state stored on a FastAPI app (``app.state.domino``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from domino.uow.unit_of_work import AsyncUnitOfWork, UnitOfWork


@dataclass
class DominoState:
    """What the per-request dependencies need, held on ``app.state.domino``.

    Attributes:
        unit_of_work_factory: a zero-arg callable returning a fresh unit of work.
            The dependency calls it once per request, so no two requests share a
            session, a repository set or an event queue.
    """

    unit_of_work_factory: Callable[[], UnitOfWork | AsyncUnitOfWork]
