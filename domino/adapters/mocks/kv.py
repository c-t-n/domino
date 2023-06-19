from typing import Any
from domino.domain.repositories import AbstractCRUDRepository, BaseT, CreateT, UpdateT
from domino.exceptions import PrimaryKeyPropertyNotDefined


class MockedKVRepository(AbstractCRUDRepository[BaseT, CreateT, UpdateT]):
    primary_key_property: str
    base_model: type[BaseT]

    def __init__(self):
        self.__index = 1
        self.__data = dict[str, BaseT]()
        try:
            self.__getattribute__("primary_key_property")
        except AttributeError:
            raise PrimaryKeyPropertyNotDefined()

    def get(self, id: Any) -> BaseT | None:
        return self.__data.get(str(id), None)

    def list(self, filter_data: dict) -> list[BaseT]:
        return [
            data
            for data in self.__data.values()
            if all([
                data[key] == value
                for key, value in filter_data.items()
            ])
        ]

    def create(self, data: CreateT) -> BaseT:
        if self.primary_key_property not in data.schema():
            item_id = str(self.__index)
            self.__index += 1
        else:
            item_id = str(data[self.primary_key_property])

        item: BaseT = self.base_model(
            **{self.primary_key_property: item_id, **data.dict(exclude_none=True)})  # type: ignore
        self.__data[item_id] = item
        return item

    def update(self, item_id: Any, data: UpdateT) -> BaseT:
        to_update = self.__data[str(item_id)]
        item: BaseT = to_update.copy(update=data.dict(exclude_none=True))
        self.__data[str(item_id)] = item
        return item

    def delete(self, id: Any) -> None:
        del self.__data[id]
