from domino.domain.models.pydantic import DTO, Entity


class Task(Entity):
    id: int
    title: str
    description: str
    done: bool

    def set_as_done(self):
        self.done = True
        return self


class TaskCreate(DTO):
    title: str
    description: str | None = None


class TaskUpdate(DTO):
    title: str | None = None
    description: str | None = None
    done: bool | None = None
