from typing import Any, Generic, TypeVar

from domino.domain.models.pydantic import Entity, DTO
from domino.exceptions import ItemNotFound

BaseT = TypeVar("BaseT", bound=Entity)
CreateT = TypeVar("CreateT", bound=DTO)
UpdateT = TypeVar("UpdateT", bound=DTO)


class PrimaryKeyPropertyNotDefined(Exception):
    pass


class MockedKVRepository(Generic[BaseT, CreateT, UpdateT]):
    """
    A Mocked KV Repository that stores data in memory and acts as a KV store.

    It is useful for testing purposes. It is not meant to be used in production.

    It is a generic class that receives 3 type parameters:
    - BaseT: The DomainModel that will be used to store data in memory.
    - CreateT: The DTO that will be used to create new items.
    - UpdateT: The DTO that will be used to update existing items.
    """

    entity: type[BaseT]
    primary_key_property: str = "id"
    foreign_keys: dict[str, Any] = {}
    fixtures: list[CreateT] = []

    def __init__(self):
        self.__index = 1
        self._data = {}

        # Instanciate Foreign Keys repos
        self.foreign_keys = {
            key: repo_class() for key, repo_class in self.foreign_keys.items()
        }

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

    def list(self, filter_data: dict = {}) -> tuple[int, list[BaseT]]:
        return (
            len(self._data.items()),
            list(
                [
                    data
                    for data in self._data.values()
                    if all(
                        [
                            data.model_dump().get(key) == value
                            for key, value in filter_data.items()
                        ]
                    )
                ]
            ),
        )

    def create(self, data: CreateT) -> BaseT:
        if self.primary_key_property not in data.model_dump().keys():
            item_id = str(self.__index)
            self.__index += 1
        else:
            item_id = str(data.model_dump().get(self.primary_key_property))

        item_in_db: BaseT = self.entity(
            **{
                self.primary_key_property: item_id,
                **self.__resolve_foreign_keys(data),
                **data.model_dump(exclude_none=True),
            }
        )

        self._data[item_id] = item_in_db

        return item_in_db

    def update(self, item_id: int, data: UpdateT) -> BaseT:
        to_update = self._data[str(item_id)]
        self._data[str(item_id)] = self.entity(
            **{
                **to_update.dict(),
                **data.model_dump(exclude_none=True),
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

            if not fkey_id:
                continue

            try:
                resolved_fkeys[fkey] = repo.get(fkey_id)
            except ItemNotFound:
                pass

        return resolved_fkeys
