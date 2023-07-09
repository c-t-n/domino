from pydantic import BaseModel


class DomainModel(BaseModel):

    class Config:
        orm_mode = True

class DTO(BaseModel):
    pass
