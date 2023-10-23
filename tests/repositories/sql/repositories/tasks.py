from sqlalchemy import ForeignKey, desc, literal_column, select, insert
from sqlalchemy.orm import Mapped, mapped_column, relationship
from domino.exceptions import ItemNotFound

from domino.repositories.sql.sqlalchemy.repository import SQLRepository
from tests.repositories.sql.app.repositories import AbstractTaskRepository
from tests.repositories.sql.app.models import (
    Task,
    TaskCreate,
    TaskUpdate,
)
from tests.repositories.sql.repositories.users import UserMapping

from .db import Base


class TaskMapping(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str]
    description: Mapped[str]
    is_done: Mapped[bool] = mapped_column(default=False)

    user: Mapped[UserMapping] = relationship(back_populates="tasks")


class TaskRepository(SQLRepository, AbstractTaskRepository):
    def get(self, id: int) -> Task:
        query = select(TaskMapping).join(UserMapping).where(TaskMapping.id == id)

        data = self.session.execute(query).fetchone()
        if data is None:
            raise ItemNotFound
        return Task.model_validate(data[0])

    def create(self, data: TaskCreate) -> Task:
        task = TaskMapping(**data.model_dump())
        self.session.add(task)
        self.session.flush()
        self.session.refresh(task)
        return Task.model_validate(task)

    def update(self, id: int, data: TaskUpdate) -> Task:
        obj = self.session.get(TaskMapping, id)
        self.session.query(TaskMapping).filter_by(id=id).update(
            data.model_dump(exclude_none=True)  # type: ignore
        )
        self.session.refresh(obj)
        return Task.model_validate(obj)

    def list(self, filter_data: dict) -> tuple[int, list[Task]]:
        query = (
            self.session.query(TaskMapping)
            .filter_by(**filter_data)
            .order_by(desc("id"))
        )

        return (
            query.count(),
            [Task.model_validate(user) for user in query.all()],
        )

    def delete(self, id: int) -> None:
        self.session.query(TaskMapping).filter_by(id=id).delete()
