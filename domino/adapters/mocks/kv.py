from abc import ABC
from typing import Any, Generic, List, TypeVar

from domino.domain.models.pydantic import DomainModel, DTO

BaseT = TypeVar("BaseT", bound=DomainModel)
CreateT = TypeVar("CreateT", bound=DTO)
UpdateT = TypeVar("UpdateT", bound=DTO)

class ItemNotFound(Exception):
    pass


class PrimaryKeyPropertyNotDefined(Exception):
    pass


class MockedKVRepository(ABC, Generic[BaseT, CreateT, UpdateT]):
    base_model: type[BaseT]
    primary_key_property: str = "id"
    foreign_keys: dict[str, Any] = {}
    fixtures: list[CreateT] = []

    def __init__(self):
        self.__index = 1
        self._data = {}

        # Instanciate Foreign Keys repos
        self.foreign_keys = {key: repo_class() for key, repo_class in self.foreign_keys.items()}

        # Create Fixtures
        for fixture in self.fixtures:
            self.create(fixture)
        try:
            self.__getattribute__("primary_key_property")
        except AttributeError:
            raise PrimaryKeyPropertyNotDefined()

    def get(self, id: int) -> BaseT:
        try:
            return self._data[str(id)]
        except Exception:
            raise ItemNotFound

    def list(self, filter_data: dict = {}) -> list[BaseT]:
        return [
            data
            for data in self._data.values()
            if all([data.dict().get(key) == value for key, value in filter_data.items()])
        ]

    def create(self, data: CreateT) -> BaseT:
        if self.primary_key_property not in data.dict().keys():
            item_id = str(self.__index)
            self.__index += 1
        else:
            item_id = str(data.dict().get(self.primary_key_property))

        item_in_db: BaseT = self.base_model(
            **{
                self.primary_key_property: item_id,
                **self.__resolve_foreign_keys(data),
                **data.dict(exclude_none=True),
            }
        )

        self._data[item_id] = item_in_db
        
        return item_in_db

    def update(self, item_id: int, data: UpdateT) -> BaseT:
        to_update = self._data[str(item_id)]
        self._data[str(item_id)] = self.base_model(
            **{
                **to_update.dict(),
                **data.dict(exclude_none=True),
                **self.__resolve_foreign_keys(data),
            }
        )
        return self._data[str(item_id)]

    def delete(self, id: Any) -> None:
        del self._data[id]

    def __resolve_foreign_keys(self, item: CreateT | UpdateT):
        resolved_fkeys = dict()
        for fkey, repo in self.foreign_keys.items():
            fkey_id = item.dict().get(f"{fkey.lower()}_id")
            try:
                resolved_fkeys[fkey] = repo.get(fkey_id)
            except ItemNotFound:
                pass

        return resolved_fkeys
