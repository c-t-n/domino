from .repositories import AbstractUserRepository, AbstractTaskRepository
from .models import Task, TaskCreate

from domino.domain import AbstractUnitOfWork, Service


class TaskUnitOfWork(AbstractUnitOfWork):
    users: AbstractUserRepository
    tasks: AbstractTaskRepository


class TaskService(Service[TaskUnitOfWork]):
    def create_task(self, data: TaskCreate) -> Task:
        return self.unit_of_work.tasks.create(data)

    def delete_task(self, task_id: int) -> None:
        self.unit_of_work.tasks.delete(task_id)
