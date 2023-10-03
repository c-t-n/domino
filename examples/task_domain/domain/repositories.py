from domino.domain.repositories import (
    CreateRepositoryMixin,
    GetRepositoryMixin,
    SaveRepositoryMixin,
)
from .models import Task, TaskCreate


class AbstractTaskRepository(
    GetRepositoryMixin[Task],
    CreateRepositoryMixin[Task, TaskCreate],
    SaveRepositoryMixin[Task],
):
    pass
