"""DomainId — a typed wrapper around entity identifiers.

Wraps either a ``UUID`` (the default) or a ``str`` so the domain layer works
with identities uniformly. New identifiers are UUID v4 by default; string
identifiers (e.g. ``"ORD-2024-001"``) are supported by constructing directly.
"""

from __future__ import annotations

from uuid import UUID, uuid4


class DomainId:
    """A domain identifier backed by a ``UUID`` or a ``str``.

    Usage::

        order_id = DomainId.generate()      # random UUID-based id
        code_id = DomainId("ORD-2024-001")  # string-based id
        empty = DomainId.empty()            # "not yet assigned" sentinel
    """

    __slots__ = ("_value",)

    _EMPTY_UUID = UUID(int=0)

    def __init__(self, value: UUID | str) -> None:
        if not isinstance(value, (UUID, str)):
            raise TypeError(f"DomainId accepts UUID or str, got {type(value).__name__}")
        self._value: UUID | str = value

    @classmethod
    def generate(cls) -> DomainId:
        """Generate a new random (UUID v4) identifier."""
        return cls(uuid4())

    @classmethod
    def empty(cls) -> DomainId:
        """Return the "empty" / not-yet-assigned identifier."""
        return cls(cls._EMPTY_UUID)

    @property
    def value(self) -> UUID | str:
        """The underlying identifier value."""
        return self._value

    def is_empty(self) -> bool:
        """Return True if this identifier is in its empty state."""
        if isinstance(self._value, UUID):
            return self._value.int == 0
        return self._value == ""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, DomainId) and self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __str__(self) -> str:
        return str(self._value)

    def __repr__(self) -> str:
        return f"DomainId({self._value!r})"

    def __lt__(self, other: DomainId) -> bool:
        return str(self._value) < str(other._value)
