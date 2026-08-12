"""ValueObject base class.

Value objects are immutable and compared by their attributes, not by
identity: two value objects with the same data are equal.

Just subclass :class:`ValueObject` and declare fields — the base turns every
subclass into a frozen dataclass for you, so you get value equality, hashing
and immutability without repeating ``@dataclass(frozen=True)`` everywhere::

    from decimal import Decimal
    from domino import ValueObject, DomainValidationError

    class Money(ValueObject):
        amount: Decimal
        currency: str

        def __post_init__(self) -> None:
            if self.amount < 0:
                raise DomainValidationError("amount cannot be negative")

Do **not** add ``@dataclass`` yourself — the base already applies it.
"""

from __future__ import annotations

import dataclasses
from typing import Any, TypeVar, cast, dataclass_transform

_Self = TypeVar("_Self", bound="ValueObject")


@dataclass_transform(frozen_default=True)
class ValueObject:
    """Marker base that turns each subclass into a frozen dataclass."""

    __slots__ = ()

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        dataclasses.dataclass(frozen=True)(cls)

    def replace(self: _Self, **changes: Any) -> _Self:
        """Return a copy with the given fields replaced (original untouched)."""
        # The base is not itself a dataclass, but every concrete value object
        # is; dataclasses.replace only makes sense on those subclasses.
        return dataclasses.replace(cast("Any", self), **changes)
