from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class SQLDatabase:
    dsn: str | None = None
    username: str | None = None
    password: str | None = None
    host: str | None = None
    port: int | None = 5432
    database: str | None = None
    driver: str = "postgresql"

    def __init__(self):
        """
        Initializes a new instance of the SQLDatabase class.
        """
        self._engine = create_engine(self.computed_dsn)
        self._sessionmaker = sessionmaker(bind=self._engine)

    def generate_session(self) -> Session:
        """
        Generates a new session for the database.
        """
        return self._sessionmaker()

    def create_database_from_declarative_base(self, base: type[DeclarativeBase]):
        """
        Creates the database from a declarative base.

        Parameters:
        -----------
        base : DeclarativeBase
            The declarative base to create the database from.
        """
        base.metadata.create_all(self._engine)

    @property
    def computed_dsn(self):
        """
        Returns the DSN (Data Source Name) for the database.
        """
        config = dir(self)
        if "dsn" in config and self.dsn is not None:
            return self.dsn

        if self.username and self.password:
            credentials = f"{self.username}:{self.password}@"
        else:
            credentials = ""

        return f"postgresql://{credentials}{self.host}:{self.port}/{self.database}"
