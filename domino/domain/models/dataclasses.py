from dataclasses import dataclass

from domino.domain.models.abstract import (
    AbstractEntity,
    AbstractDTO,
    AbstractAggregate,
    AbstractValueObject,
)


@dataclass(frozen=True)
class ValueObject(AbstractValueObject):
    def dump(self):
        return self.__dict__


@dataclass
class Entity(AbstractEntity):
    def dump(self):
        return self.__dict__


@dataclass
class Aggregate(AbstractAggregate):
    def dump(self):
        return self.__dict__


@dataclass
class DTO(AbstractDTO):
    def dump(self):
        return self.__dict__
