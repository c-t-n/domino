from sqlalchemy.orm import DeclarativeBase
from domino.repositories.sql.sqlalchemy.database import SQLDatabase


class TaskSQLDatabase(SQLDatabase):
    class Config:
        dsn = "sqlite://"


class Base(DeclarativeBase):
    pass
