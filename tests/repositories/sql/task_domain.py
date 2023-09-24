from domino.domain.models.pydantic import DTO, Entity
from domino.domain.repositories import AbstractCRUDRepository


class User(Entity):
    id: int
    name: str
    email: str


class UserCreate(DTO):
    name: str
    email: str


class UserUpdate(DTO):
    name: str | None = None
    email: str | None = None


class AbstractUserRepository(AbstractCRUDRepository[User, UserCreate, UserUpdate]):
    pass


class Task(Entity):
    id: int
    title: str
    description: str
    is_done: bool = False


class TaskCreate(DTO):
    title: str
    description: str


class TaskUpdate(DTO):
    title: str | None = None
    description: str | None = None
    is_done: bool | None = None


class AbstractTaskRepository(AbstractCRUDRepository[Task, TaskCreate, TaskUpdate]):
    pass
