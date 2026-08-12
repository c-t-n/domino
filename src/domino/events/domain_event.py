"""DomainEvent — an immutable record of something meaningful that happened.

Domain events are named in the past tense (``OrderConfirmed``, ``PaymentFailed``)
and carry only the data a handler needs. Just subclass :class:`DomainEvent` and
declare the payload fields — the base makes every subclass a frozen,
keyword-only dataclass and supplies ``event_id`` and ``occurred_on`` for you::

    class OrderConfirmed(DomainEvent):
        order_id: DomainId
        customer_id: DomainId
        total: str

    event = OrderConfirmed(order_id=..., customer_id=..., total="42.00")
    # event.event_id and event.occurred_on are filled in automatically.

Keyword-only construction lets subclasses add required fields after the base's
defaulted ones. Do **not** add ``@dataclass`` yourself — the base applies it.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import dataclass_transform
from uuid import UUID, uuid4

from domino.core.correlation import get_correlation_id


@dataclass_transform(frozen_default=True, kw_only_default=True)
@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Base class for all domain events.

    Provides a unique ``event_id``, an ``occurred_on`` timestamp, and the
    ambient ``correlation_id`` — all filled in automatically. Subclasses add
    their own immutable payload fields. The correlation id is captured from the
    surrounding :func:`~domino.core.correlation.correlation_scope` (a use case
    opens one for you), so an event always knows which operation produced it.
    """

    event_id: UUID = field(default_factory=uuid4)
    occurred_on: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = field(default_factory=get_correlation_id)

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        dataclasses.dataclass(frozen=True, kw_only=True)(cls)

    @property
    def event_name(self) -> str:
        """The class name, used for handler routing."""
        return type(self).__name__
