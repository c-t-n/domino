import pytest

from domino.domain.repositories.mocks import MockedKVRepository
from domino.domain.models.pydantic import DomainModel
from domino.exceptions.repositories import PrimaryKeyPropertyNotDefined

class DummyModel(DomainModel):
    id: str
    login: str


class DummyKVRepository(MockedKVRepository[DummyModel]):
    primary_key_property = "id"
    model: DummyModel

class TestMockedKVStore:
    
    def initialize_dataset(self):
        kvstore = DummyKVRepository()

        kvstore.create(DummyModel(id="1", login="test-one"))
        kvstore.create(DummyModel(id="2", login="test-two"))
        kvstore.create(DummyModel(id="3", login="test-three"))
        return kvstore

    def test_can_initialize(self):
        DummyKVRepository()

    def test_raise_an_exception_when_init_with_repository_and_uow(self):
        with pytest.raises(PrimaryKeyPropertyNotDefined):
            MockedKVRepository()

    def test_get_data_from_id(self):
        store = self.initialize_dataset()

        assert store.get("1") == {"id": "1", "login": "test-one"}
        assert store.get("2") == {"id": "2", "login": "test-two"}
        assert store.get("3") == {"id": "3", "login": "test-three"}


    def test_fetch_data_on_simple_criterions(self):
        store = self.initialize_dataset()

        store.create(DummyModel(id="4", login= "test-two"))

        assert store.list({"login": "test-two"}) == [
            {"id": "2", "login": "test-two"},
            {"id": "4", "login": "test-two"}
        ]
