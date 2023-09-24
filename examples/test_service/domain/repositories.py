from domino.domain.repositories import AbstractCRUDRepository
from test_service.domain.models import Task, TaskCreate, TaskUpdate


class AbstractTaskRepository(AbstractCRUDRepository[Task, TaskCreate, TaskUpdate]):
    pass
