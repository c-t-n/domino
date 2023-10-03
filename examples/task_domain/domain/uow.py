from domino.domain import UnitOfWork

from .repositories import AbstractTaskRepository


class AbstractTaskUnitOfWork(UnitOfWork):
    tasks: AbstractTaskRepository
