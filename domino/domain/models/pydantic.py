from pydantic import BaseModel
from typing import Any

class DomainModel(BaseModel):

    def __getitem__(self, __name: str) -> Any:
        return self.__dict__.get(__name)

    class Config:
        orm_mode = True