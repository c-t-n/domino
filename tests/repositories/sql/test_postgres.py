import pytest

from domino.exceptions import ItemNotFound
from tests.repositories.sql.app.models import TaskCreate, TaskUpdate, UserCreate
from tests.repositories.sql.app.services import TaskService, TaskUnitOfWork
from tests.repositories.sql.repositories.db import Base, InMemoryDatabase
from tests.repositories.sql.repositories.tasks import TaskRepository
from tests.repositories.sql.repositories.users import UserRepository


class InMemoryTaskUnitOfWork(TaskUnitOfWork):
    def __init__(self):
        self.database = InMemoryDatabase()

    def begin(self):
        self.session = self.database.generate_session()
        self.users = UserRepository(self.session)
        self.tasks = TaskRepository(self.session)

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


@pytest.fixture
def uow():
    unit_of_work = InMemoryTaskUnitOfWork()
    unit_of_work.database.create_database_from_declarative_base(Base)

    # Fixtures
    with unit_of_work:
        for user in [
            UserCreate(name="John Doe", email="jdoe@42.fr"),
            UserCreate(name="Jane Doe", email="jadoe@42.fr"),
        ]:
            unit_of_work.users.create(user)

    with unit_of_work:
        for task in [
            TaskCreate(
                title="Test task 1", description="Test description 1", user_id=1
            ),
        ]:
            unit_of_work.tasks.create(task)

    return unit_of_work


class TestPostgresRepository:
    def test_retrieve_first_user(self, uow: InMemoryTaskUnitOfWork):
        user = uow.users.get(1)

        assert user.id == 1
        assert user.name == "John Doe"
        assert user.email == "jdoe@42.fr"

    def test_create_task(self, uow: InMemoryTaskUnitOfWork):
        with uow:
            svc = TaskService(uow)
            payload = TaskCreate(
                title="Test task",
                description="Test description",
                user_id=1,
            )
            task = svc.create_task(payload)

        assert task.id == 2
        assert task.title == "Test task"
        assert task.description == "Test description"
        assert task.user.id == 1
        assert "user_id" not in task.dump().keys()

    def test_can_delete_a_task(self, uow: InMemoryTaskUnitOfWork):
        with uow:
            uow.tasks.delete(1)

    def test_cant_create_data_when_transaction_is_interrupted(
        self, uow: InMemoryTaskUnitOfWork
    ):
        id = None
        with pytest.raises(Exception):
            with uow:
                svc = TaskService(uow)
                payload = TaskCreate(
                    title="Test task",
                    description="Test description",
                    user_id=1,
                )
                task = svc.create_task(payload)
                id = task.id
                raise Exception("Interrupted transaction")

        with pytest.raises(ItemNotFound):
            assert id is not None
            uow.tasks.get(id)

    def test_can_update_a_task(self, uow: InMemoryTaskUnitOfWork):
        with uow:
            task = uow.tasks.update(
                1, TaskUpdate(title="Test task 2", description="Test description")
            )

        with uow:
            task = uow.tasks.get(task.id)
            assert task.title == "Test task 2"
            assert task.description == "Test description"
            assert task.user.id == 1
            assert "user_id" not in task.dump().keys()

    def test_can_delete_and_rollback(self, uow: InMemoryTaskUnitOfWork):
        with pytest.raises(Exception):
            with uow:
                uow.tasks.delete(1)
                raise Exception()

        with uow:
            task = uow.tasks.get(1)
            assert task.title == "Test task 1"
            assert task.description == "Test description 1"
            assert task.user.id == 1
            assert "user_id" not in task.dump().keys()
