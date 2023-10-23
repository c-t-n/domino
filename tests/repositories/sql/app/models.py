from domino.domain.models.pydantic import DTO, Entity


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


class Task(Entity):
    id: int
    user: User
    title: str
    description: str
    is_done: bool = False


class TaskCreate(DTO):
    title: str
    description: str
    user_id: int


class TaskUpdate(DTO):
    title: str | None = None
    description: str | None = None
    is_done: bool | None = None
