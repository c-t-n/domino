from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domino.exceptions import ItemNotFound
from domino.repositories.sql.sqlalchemy.repository import SQLCRUDRepository
from tests.repositories.sql.app.models import Task, TaskCreate, TaskUpdate
from tests.repositories.sql.app.repositories import AbstractTaskRepository
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


class TaskRepository(
    AbstractTaskRepository, SQLCRUDRepository[Task, TaskCreate, TaskUpdate]
):
    sql_mapping = TaskMapping
    domain_mapping = Task
