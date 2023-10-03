from sqlalchemy import desc
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from domino.domain.uow import UnitOfWork
from domino.exceptions import ItemNotFound
from domino.repositories.sql.sqlalchemy.database import SQLDatabase
from domino.repositories.sql.sqlalchemy.repository import SQLRepository
from tests.repositories.sql.task_domain import (
    AbstractUserRepository,
    User,
    UserCreate,
    UserUpdate,
)


class InMemoryDatabase(SQLDatabase):
    class Config:
        dsn = "sqlite://"


class Base(DeclarativeBase):
    pass


class UserMapping(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str]


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

    class Config:
        database = InMemoryDatabase


class AbstractUserUnitOfWork(UnitOfWork):
    user_repository: AbstractUserRepository


class UserUnitOfWork(AbstractUserUnitOfWork):
    user_repository = UserRepository()
