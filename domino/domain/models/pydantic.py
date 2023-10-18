from pydantic import BaseModel, ConfigDict

from domino.domain.models.abstract import (
    AbstractEntity,
    AbstractDTO,
    AbstractAggregate,
    AbstractValueObject,
)


class ValueObject(AbstractValueObject, BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    def dump(self):
        return self.model_dump()


class Entity(AbstractEntity, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    def dump(self):
        return self.model_dump()


class Aggregate(AbstractAggregate, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    def dump(self):
        return self.model_dump()


class DTO(AbstractDTO, BaseModel):
    def dump(self):
        return self.model_dump(exclude_none=True)
