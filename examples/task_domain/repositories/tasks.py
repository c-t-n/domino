from typing import Any
from sqlalchemy import literal_column, update
from sqlalchemy.orm import mapped_column, Mapped
from domino.exceptions import ItemNotFound

from domino.repositories.sql.sqlalchemy.repository import SQLRepository
from .database import Base, TaskSQLDatabase
from examples.task_domain.domain.repositories import AbstractTaskRepository
from examples.task_domain.domain.models import Task, TaskCreate, TaskUpdate


class TaskORM(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    description: Mapped[str]
    done: Mapped[bool] = mapped_column(default=False)


class TaskRepository(SQLRepository, AbstractTaskRepository):
    def get(self, id: Any) -> Task:
        result = self.session.query(TaskORM).get(id)
        if not result:
            raise ItemNotFound

        return Task.model_validate(result)

    def create(self, data: TaskCreate) -> Task:
        task = TaskORM(**data.dump())
        self.session.add(task)
        self.session.flush()
        self.session.refresh(task)

        return Task.model_validate(task)

    def save(self, task: Task) -> Task:
        query = (
            update(TaskORM)
            .where(TaskORM.id == task.id)
            .values(**task.dump())
            .returning(literal_column("*"))
        )

        result = self.session.execute(query).fetchone()

        return Task.model_validate(result)

    class Config:
        database = TaskSQLDatabase
