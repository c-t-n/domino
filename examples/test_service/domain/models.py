from domino.domain.models.pydantic import Entity, DTO


class Task(Entity):
    id: int
    title: str
    description: str
    done: bool = False


class TaskCreate(DTO):
    title: str
    description: str


class TaskUpdate(DTO):
    title: str | None = None
    description: str | None = None
    done: bool | None = None
