from domino.domain.uow import UnitOfWork
from test_service.domain.repositories import AbstractTaskRepository


class TaskUnitOfWork(UnitOfWork):
    task_repository: AbstractTaskRepository
