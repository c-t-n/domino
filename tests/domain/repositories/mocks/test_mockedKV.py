import pytest
from domino.exceptions import ItemNotFound

from domino.repositories.mocks.kv import MockedKVRepository
from domino.domain.models.pydantic import Entity, DTO


class Dummy(Entity):
    id: str
    login: str


class DummyCreate(DTO):
    login: str


class DummyUpdate(DTO):
    login: str | None


class DummyKVRepository(MockedKVRepository[Dummy, DummyCreate, DummyUpdate]):
    primary_key_property = "id"
    base_model = Dummy
    fixtures = [
        DummyCreate(login="test-one"),
        DummyCreate(login="test-two"),
        DummyCreate(login="test-three"),
    ]


class TestMockedKVStore:
    def setup_method(self):
        self.store = DummyKVRepository()

    def test_get_data_from_id(self):
        assert self.store.get(1) == {"id": "1", "login": "test-one"}
        assert self.store.get(2) == {"id": "2", "login": "test-two"}
        assert self.store.get(3) == {"id": "3", "login": "test-three"}

    def test_fetch_data_on_simple_criterions(self):
        self.store.create(DummyCreate(login="test-two"))

        assert self.store.list({"login": "test-two"}) == [
            Dummy(**{"id": 2, "login": "test-two"}),
            Dummy(**{"id": 4, "login": "test-two"}),
        ]

    def test_create_data(self):
        self.store.create(DummyCreate(login="test-four"))

        assert self.store.get(4) == {"id": "4", "login": "test-four"}

    def test_update_data(self):
        self.store.update(1, DummyUpdate(login="test-one-updated"))

        assert self.store.get(1) == {"id": "1", "login": "test-one-updated"}

    def test_delete_data(self):
        self.store.delete(1)

        with pytest.raises(ItemNotFound):
            self.store.get(1)
