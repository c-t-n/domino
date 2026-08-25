"""Entity base class.

Entities are defined by their **identity**, not their attributes: two entities
with the same data are still different if their ids differ, and an entity keeps
its identity while its attributes change over its lifecycle.

Just subclass :class:`Entity` and declare fields — the base makes every subclass
a mutable dataclass with ``eq=False``, so Domino's identity-based equality is
kept instead of dataclass field equality. Every entity must declare an ``_id``
field (give it a default so construction stays convenient)::

    from dataclasses import field
    from domino import DomainId, Entity

    class Customer(Entity):
        _id: DomainId = field(default_factory=DomainId.generate)
        name: str = ""

Do **not** add ``@dataclass`` yourself — the base already applies it.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import dataclass_transform

# Imported at runtime, not under TYPE_CHECKING: `_id: DomainId` must stay
# resolvable by typing.get_type_hints() for anything that introspects an
# entity's annotations — event serialization, an ORM, a schema generator.
from domino.core.id import DomainId


@dataclass_transform(eq_default=False)
class Entity(ABC):
    """Base class for all domain entities.

    Turns each subclass into a mutable dataclass with identity-based equality
    and hashing, a typed :attr:`id`, and a :meth:`is_transient` check.
    Subclasses must define an ``_id`` field.
    """

    _id: DomainId

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        dataclass(eq=False)(cls)

    @property
    def id(self) -> DomainId:
        """The unique identity of this entity."""
        return self._id

    def is_transient(self) -> bool:
        """Return True if this entity has no assigned identity yet."""
        return self._id.is_empty()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self._id!r})"
