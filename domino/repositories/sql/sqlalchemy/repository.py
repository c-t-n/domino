from typing import Generic, Type

from sqlalchemy import desc
from sqlalchemy.orm import DeclarativeBase, Session

from domino.base.baseclass import DominoBaseClass
from domino.domain.repositories import (
    BaseT,
    CreateRepositoryMixin,
    CreateT,
    DeleteRepositoryMixin,
    GetRepositoryMixin,
    ListRepositoryMixin,
    UpdateRepositoryMixin,
    UpdateT,
)
from domino.exceptions import ItemNotFound


class SQLRepository(Generic[BaseT], DominoBaseClass):
    """
    A class representing a SQL repository.

    Attributes:
    -----------
    _db: SQLDatabase
        The SQL database object.
    """

    sql_mapping: Type[DeclarativeBase]
    domain_mapping: Type[BaseT]

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session


class SQLGetMixin(GetRepositoryMixin[BaseT], SQLRepository):
    """
    A class representing a SQL get mixin.
    """

    def get(self, id: int) -> BaseT:
        data = self.session.get(self.sql_mapping, id)
        if data is None:
            raise ItemNotFound
        return self.domain_mapping.load(data)


class SQLCreateMixin(CreateRepositoryMixin[BaseT, CreateT], SQLRepository):
    """
    A class representing a SQL create mixin.
    """

    def create(self, data: CreateT) -> BaseT:
        sql_obj = self.sql_mapping(**data.dump())
        self.session.add(sql_obj)
        self.session.flush()
        self.session.refresh(sql_obj)
        return self.domain_mapping.load(sql_obj)


class SQLListMixin(ListRepositoryMixin[BaseT], SQLRepository):
    """
    A class representing a SQL list mixin.
    """

    def list(self, filter_data: dict) -> tuple[int, list[BaseT]]:
        query = (
            self.session.query(self.sql_mapping)
            .filter_by(**filter_data)
            .order_by(desc("id"))
        )

        return (
            query.count(),
            [self.domain_mapping.load(user) for user in query.all()],
        )


class SQLUpdateMixin(UpdateRepositoryMixin[BaseT, UpdateT], SQLRepository):
    """
    A class representing a SQL update mixin.
    """

    def update(self, id: int, data: UpdateT) -> BaseT:
        obj = self.session.get(self.sql_mapping, id)
        self.session.query(self.sql_mapping).filter_by(id=id).update(**data.dump())
        self.session.refresh(obj)
        return self.domain_mapping.load(obj)


class SQLDeleteMixin(DeleteRepositoryMixin[BaseT], SQLRepository):
    """
    A class representing a SQL delete mixin.
    """

    def delete(self, id: int) -> None:
        self.session.query(self.sql_mapping).filter_by(id=id).delete()


class SQLReadOnlyRepository(SQLGetMixin[BaseT], SQLListMixin[BaseT]):
    pass


class SQLWriteOnlyRepository(
    SQLCreateMixin[BaseT, CreateT],
    SQLUpdateMixin[BaseT, UpdateT],
    SQLDeleteMixin[BaseT],
):
    pass


class SQLCRUDRepository(
    SQLReadOnlyRepository[BaseT], SQLWriteOnlyRepository[BaseT, CreateT, UpdateT]
):
    pass
