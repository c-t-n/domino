"""The Domino state stored on a FastAPI app (``app.state.domino``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from domino.events.publisher import EventPublisher
from domino.sqlalchemy.async_repository import AsyncSqlAlchemyRepository


@dataclass
class DominoState:
    """What the per-request dependencies need, held on ``app.state.domino``.

    Attributes:
        session_factory: builds an :class:`AsyncSession` (an ``async_sessionmaker``
            or any zero-arg callable). Created once at startup.
        repositories: the name → repository-class mapping each unit of work is
            built from.
        event_bus: optional publisher; when set, the unit of work dispatches
            domain events after a successful commit.
    """

    session_factory: Callable[[], AsyncSession]
    repositories: dict[str, type[AsyncSqlAlchemyRepository[Any]]] = field(
        default_factory=dict
    )
    event_bus: EventPublisher | None = None
