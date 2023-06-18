from typing import Any, TypeVar
from domino.domain.repositories.base import AbstractCRUDRepository
from domino.domain.models.pydantic import DomainModel
from domino.exceptions.repositories import PrimaryKeyPropertyNotDefined

T = TypeVar('T',bound=DomainModel)


class MockedKVRepository(AbstractCRUDRepository[T]):
    primary_key_property: str
    model: T

    def __init__(self):
        self.__data = dict[str, T]()
        try:
            self.__getattribute__("primary_key_property")
        except AttributeError:
            raise PrimaryKeyPropertyNotDefined()

    def get(self, id: Any) -> T | None:
        return self.__data.get(id, None)
    
    def list(self, filter_data: dict) -> list[T]:
        return [
            data
            for data in self.__data.values()
            if all([
                data[key] == value
                for key, value in filter_data.items()
            ])
        ]

    def create(self, data: T) -> T:
        item_id = data[self.primary_key_property]
        self.__data[item_id] = data
        return data
    
    def update(self, item_id: Any, data: T) -> T:
        self.__data[item_id] = data
        return data
    
    def delete(self, id: Any) -> None:
        del self.__data[id]
