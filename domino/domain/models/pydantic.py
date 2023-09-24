from pydantic import BaseModel, ConfigDict


class Entity(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Aggregate(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DTO(BaseModel):
    pass
