from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


class SQLDatabase:
    """
    A class representing a SQL database.

    Attributes:
    -----------
    _session : Session | None
        The current session of the database.
    _engine : Engine
        The engine used to connect to the database.
    __config : Config
        The configuration object for the database.

    Methods:
    --------
    engine() -> Engine:
        Returns the engine used to connect to the database.
    session() -> Session:
        Returns the current session of the database.
    in_transaction() -> bool:
        Returns True if the database is currently in a transaction, False otherwise.
    flush_session() -> None:
        Flushes the current session of the database.
    begin() -> None:
        Begins a new transaction for the database.
    commit() -> None:
        Commits the current transaction for the database.
    rollback() -> None:
        Rolls back the current transaction for the database.
    dsn() -> str:
        Returns the DSN (Data Source Name) for the database.
    """

    _session: Session | None = None

    def __init__(self):
        """
        Initializes a new instance of the SQLDatabase class.
        """
        self.__config = self.Config()
        self._engine = create_engine(self.dsn)
        self._sessionmaker = sessionmaker(bind=self._engine)

    @property
    def engine(self):
        """
        Returns the engine used to connect to the database.
        """
        return self._engine

    @property
    def session(self):
        """
        Returns the current session of the database.
        """
        if self.__class__._session is None:
            self.__class__._session = self._sessionmaker()
        return self._session

    @property
    def in_transaction(self):
        """
        Returns True if the database is currently in a transaction, False otherwise.
        """
        if self._session is None:
            return False

        return self._session.in_transaction()

    def flush_session(self):
        """
        Flushes the current session of the database.
        """
        self.__class__._session = None

    def begin(self):
        """
        Begins a new transaction for the database.
        """
        if not self._session:
            self._session = self._sessionmaker()

        if not self.in_transaction:
            self._session.begin()

    def commit(self):
        """
        Commits the current transaction for the database.
        """
        if not self.in_transaction:
            return

        if self._session:
            self._session.commit()
            self.flush_session()

    def rollback(self):
        """
        Rolls back the current transaction for the database.
        """
        if not self.in_transaction:
            return

        if self._session:
            self._session.rollback()
            self.flush_session()

    @property
    def dsn(self):
        """
        Returns the DSN (Data Source Name) for the database.
        """
        if self.__config.dsn:
            return self.__config.dsn

        if self.__config.username and self.__config.password:
            credentials = f"{self.__config.username}:{self.__config.password}@"
        else:
            credentials = ""

        return f"postgresql://{credentials}{self.__config.host}:{self.__config.port}/{self.__config.database}"

    class Config:
        """
        A class representing the configuration object for the SQLDatabase class.

        Attributes:
        -----------
        dsn : str | None
            The DSN (Data Source Name) for the database.
        username : str | None
            The username used to connect to the database.
        password : str | None
            The password used to connect to the database.
        host : str | None
            The host name of the database.
        port : int | None
            The port number of the database.
        database : str | None
            The name of the database.
        """

        dsn: str | None
        username: str | None
        password: str | None
        host: str | None
        port: int | None
        database: str | None
