import pytest

from domino.adapters.mocks.kv import MockedKVRepository
from domino.domain.models.pydantic import DomainModel, DTO


class Dummy(DomainModel):
    id: str
    login: str


class DummyCreate(DTO):
    login: str


class DummyUpdate(DTO):
    login: str | None


class DummyKVRepository(MockedKVRepository[Dummy, DummyCreate, DummyUpdate]):
    primary_key_property = "id"
    base_model = Dummy


class TestMockedKVStore:

    def initialize_dataset(self):
        kvstore = DummyKVRepository()

        kvstore.create(DummyCreate(login="test-one"))
        kvstore.create(DummyCreate(login="test-two"))
        kvstore.create(DummyCreate(login="test-three"))
        return kvstore

    def test_can_initialize(self):
        DummyKVRepository()

    def test_get_data_from_id(self):
        store = self.initialize_dataset()

        assert store.get(1) == {"id": "1", "login": "test-one"}
        assert store.get(2) == {"id": "2", "login": "test-two"}
        assert store.get(3) == {"id": "3", "login": "test-three"}

    def test_fetch_data_on_simple_criterions(self):
        store = self.initialize_dataset()

        store.create(DummyCreate(login="test-two"))

        assert store.list({"login": "test-two"}) == [
            Dummy(**{"id": 2, "login": "test-two"}),
            Dummy(**{"id": 4, "login": "test-two"})
        ]
