"""SQLAlchemy column type for :class:`~domino.core.id.DomainId`."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from domino.core.id import DomainId


class DomainIdType(TypeDecorator[DomainId]):
    """Stores a :class:`DomainId` as text and rebuilds it on load.

    UUID-backed ids round-trip as UUIDs and string-backed ids as strings. The one
    ambiguity: a *string* id that happens to be UUID-shaped is reconstructed as a
    UUID — so use one id style consistently per column.

    The stored column is ``String(length)`` (default 36, enough for a UUID); pass
    a larger length for longer string ids: ``Column("id", DomainIdType(64))``.
    """

    impl = String
    cache_ok = True

    def __init__(self, length: int = 36, **kwargs: Any) -> None:
        super().__init__(length=length, **kwargs)

    def process_bind_param(
        self, value: DomainId | None, dialect: Dialect
    ) -> str | None:
        return None if value is None else str(value)

    def process_result_value(
        self, value: str | None, dialect: Dialect
    ) -> DomainId | None:
        if value is None:
            return None
        try:
            return DomainId(UUID(value))
        except ValueError:
            return DomainId(value)
