from .models import User, UserCreate, UserUpdate, Task, TaskCreate, TaskUpdate
from domino.domain.repositories import AbstractCRUDRepository


class AbstractUserRepository(AbstractCRUDRepository[User, UserCreate, UserUpdate]):
    pass


class AbstractTaskRepository(AbstractCRUDRepository[Task, TaskCreate, TaskUpdate]):
    pass
