from sqlalchemy import desc
from sqlalchemy.orm import Mapped, mapped_column, relationship
from domino.exceptions import ItemNotFound

from domino.repositories.sql.sqlalchemy.repository import SQLRepository
from tests.repositories.sql.app.repositories import AbstractUserRepository
from tests.repositories.sql.app.models import (
    User,
    UserCreate,
    UserUpdate,
)

from .db import Base


class UserMapping(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str]

    tasks = relationship("TaskMapping", back_populates="user")


class UserRepository(SQLRepository, AbstractUserRepository):
    def get(self, id: int) -> User:
        data = self.session.get(UserMapping, id)
        if data is None:
            raise ItemNotFound
        return User.model_validate(data)

    def create(self, data: UserCreate) -> User:
        user = UserMapping(**data.model_dump())
        self.session.add(user)
        self.session.flush()
        self.session.refresh(user)
        return User.model_validate(user)

    def update(self, id: int, data: UserUpdate) -> User:
        obj = self.session.get(UserMapping, id)
        self.session.query(UserMapping).filter_by(id=id).update(**data.model_dump())
        self.session.refresh(obj)
        return User.model_validate(obj)

    def list(self, filter_data: dict) -> tuple[int, list[User]]:
        query = (
            self.session.query(UserMapping)
            .filter_by(**filter_data)
            .order_by(desc("id"))
        )

        return (
            query.count(),
            [User.model_validate(user) for user in query.all()],
        )

    def delete(self, id: int) -> None:
        self.session.query(UserMapping).filter_by(id=id).delete()
