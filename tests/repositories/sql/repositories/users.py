from sqlalchemy import desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domino.exceptions import ItemNotFound
from domino.repositories.sql.sqlalchemy.repository import (
    SQLCRUDRepository,
    SQLRepository,
)
from tests.repositories.sql.app.models import User, UserCreate, UserUpdate
from tests.repositories.sql.app.repositories import AbstractUserRepository

from .db import Base


class UserMapping(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str]

    tasks = relationship("TaskMapping", back_populates="user")


class UserRepository(
    AbstractUserRepository, SQLCRUDRepository[User, UserCreate, UserUpdate]
):
    sql_mapping = UserMapping
    domain_mapping = User
