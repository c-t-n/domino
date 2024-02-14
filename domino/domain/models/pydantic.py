from pydantic import BaseModel, ConfigDict

from domino.domain.models.abstract import (AbstractAggregate, AbstractDTO,
                                           AbstractEntity, AbstractValueObject)


class ValueObject(AbstractValueObject, BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    @classmethod
    def load(cls, data):
        return cls.model_validate(data)
    
    def dump(self):
        return self.model_dump()


class Entity(AbstractEntity, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def load(cls, data):
        return cls.model_validate(data)
    
    def dump(self):
        return self.model_dump()


class Aggregate(AbstractAggregate, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def load(cls, data):
        return cls.model_validate(data)
    
    def dump(self):
        return self.model_dump()


class DTO(AbstractDTO, BaseModel):
    @classmethod
    def load(cls, data):
        return cls.model_validate(data)
    
    def dump(self):
        return self.model_dump(exclude_none=True)
