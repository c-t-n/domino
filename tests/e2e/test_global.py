from domino.domain.repositories import AbstractCRUDRepository
from domino.domain.services import Service
from domino.domain.models.pydantic import Entity, DTO
from domino.domain.uow import UnitOfWork
from domino.repositories.mocks.kv import MockedKVRepository


class Task(Entity):
    id: int
    title: str
    description: str
    done: bool = False


class TaskCreate(DTO):
    title: str
    description: str


class TaskUpdate(DTO):
    title: str | None = None
    description: str | None = None
    done: bool | None = None


class AbstractTaskRepository(AbstractCRUDRepository[Task, TaskCreate, TaskUpdate]):
    pass


class TaskUnitOfWork(UnitOfWork):
    task_repository: AbstractTaskRepository


class MockedTaskRepository(MockedKVRepository, AbstractTaskRepository):
    entity = Task
    fixtures = [
        TaskCreate(title="Task 1", description="Task 1 description"),
        TaskCreate(title="Task 2", description="Task 2 description"),
    ]


class MockedTaskUnitOfWork(TaskUnitOfWork):
    task_repository = MockedTaskRepository()


class TasksService(Service[TaskUnitOfWork]):
    def create_task(self, data: TaskCreate) -> Task:
        with self.unit_of_work as uow:
            task = uow.task_repository.create(data)

        return task

    def update_task(self, id: int, data: TaskUpdate) -> Task:
        with self.unit_of_work as uow:
            task = uow.task_repository.update(id, data)

        return task

    def delete_task(self, id: int) -> None:
        with self.unit_of_work as uow:
            uow.task_repository.delete(id)

    def set_task_as_done(self, id: int) -> Task:
        with self.unit_of_work as uow:
            task = uow.task_repository.update(id, TaskUpdate(done=True))

        return task

    def set_task_as_undone(self, id: int) -> Task:
        with self.unit_of_work as uow:
            task = uow.task_repository.update(id, TaskUpdate(done=False))

        return task
