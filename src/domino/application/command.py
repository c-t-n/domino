"""Command — an immutable request handled by a use case.

A command is a plain, frozen data object that describes an intent ("place this
order"). Unlike an entity it has no identity, and unlike a domain event it is a
request about to happen rather than a record of what already did. It carries
only the inputs a :class:`~domino.application.use_case.UseCase` needs.

Just subclass :class:`Command` and declare fields — the base makes it a frozen
dataclass for you::

    from domino import Command, DomainId

    class PlaceOrder(Command):
        customer_id: DomainId
        items: list[tuple[str, int]]

Do **not** add ``@dataclass`` yourself — the base already applies it.
"""

from __future__ import annotations

import dataclasses
from typing import dataclass_transform


@dataclass_transform(frozen_default=True)
class Command:
    """Marker base that turns each subclass into a frozen dataclass DTO."""

    __slots__ = ()

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        dataclasses.dataclass(frozen=True)(cls)
