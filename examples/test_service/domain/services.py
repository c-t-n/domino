from domino.domain.services import Service
from test_service.domain.uow import TaskUnitOfWork
from test_service.domain.models import Task, TaskCreate, TaskUpdate


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
