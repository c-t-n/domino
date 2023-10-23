from sqlalchemy.orm import DeclarativeBase
from domino.repositories.sql.sqlalchemy.database import SQLDatabase


class InMemoryDatabase(SQLDatabase):
    dsn = "sqlite:///:memory:"


class Base(DeclarativeBase):
    pass
