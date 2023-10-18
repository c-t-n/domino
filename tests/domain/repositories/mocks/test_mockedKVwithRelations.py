import pytest
from domino.exceptions import ItemNotFound

from domino.repositories.mocks.kv import MockedKVRepository
from domino.domain.models.pydantic import Entity, DTO


class User(Entity):
    id: int
    login: str


class UserCreate(DTO):
    login: str


class UserUpdate(DTO):
    login: str | None = None


class Task(Entity):
    id: int
    name: str
    user: User


class TaskCreate(DTO):
    name: str
    user_id: int


class TaskUpdate(DTO):
    name: str | None = None
    user_id: int | None = None


class UserRepository(MockedKVRepository[User, UserCreate, UserUpdate]):
    entity = User
    fixtures = [
        UserCreate(login="test-one"),
        UserCreate(login="test-two"),
        UserCreate(login="test-three"),
    ]


class TaskRepository(MockedKVRepository[Task, TaskCreate, TaskUpdate]):
    entity = Task
    fixtures = [
        TaskCreate(name="test-one", user_id=1),
        TaskCreate(name="test-two", user_id=1),
        TaskCreate(name="test-three", user_id=2),
        TaskCreate(name="test-four", user_id=3),
    ]
    foreign_keys = {"user": UserRepository}


class TestMockedKVStoreWithForeignKeys:
    def setup_method(self):
        self.store = TaskRepository()

    def test_should_get_a_task_with_user(self):
        assert self.store.get(1).dump() == {
            "id": 1,
            "name": "test-one",
            "user": {"id": 1, "login": "test-one"},
        }

    def test_should_change_user(self):
        self.store.update(1, TaskUpdate(user_id=2))

        assert self.store.get(1).dump() == {
            "id": 1,
            "name": "test-one",
            "user": {"id": 2, "login": "test-two"},
        }
