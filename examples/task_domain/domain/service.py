from domino.domain import Service
from .models import Task, TaskCreate, TaskUpdate
from .uow import AbstractTaskUnitOfWork


class TaskService(Service[AbstractTaskUnitOfWork]):
    def create_task(self, data: TaskCreate) -> Task:
        with self.unit_of_work as uow:
            return uow.tasks.create(data)

    def update_task(self, id: int, data: TaskUpdate) -> Task:
        task = self.unit_of_work.tasks.get(id)
        updated_task = task.model_copy(**data.model_dump(exclude_none=True))

        with self.unit_of_work as uow:
            return uow.tasks.save(updated_task)

    def set_task_as_done(self, id: int) -> Task:
        task = self.unit_of_work.tasks.get(id)
        task.set_as_done()

        with self.unit_of_work as uow:
            return uow.tasks.save(task)
