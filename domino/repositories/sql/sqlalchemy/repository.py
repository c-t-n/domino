from domino.repositories.sql.sqlalchemy.database import SQLDatabase


class SQLRepository:
    """
    A class representing a SQL repository.

    Attributes:
    -----------
    _db: SQLDatabase
        The SQL database object.
    """

    def __init__(self):
        """
        Initializes a new instance of the SQLRepository class.
        """
        if "database" not in self.Config.__dict__.keys():
            raise ValueError("PostgresRepository.Config must have a database attribute")

        self._db = self.Config.database()

    @property
    def in_transaction(self):
        """
        Gets a value indicating whether the repository is in a transaction.

        Returns:
        --------
        bool
            True if the repository is in a transaction; otherwise, False.
        """
        return self._db.in_transaction

    @property
    def session(self):
        """
        Gets the session object for the repository.

        Returns:
        --------
        Session
            The session object for the repository.
        """
        if not self._db.session:
            raise ValueError("Repository must be in transaction")
        return self._db.session

    @property
    def engine(self):
        """
        Gets the engine object for the repository.

        Returns:
        --------
        Engine
            The engine object for the repository.
        """
        return self._db.engine

    def begin(self):
        """
        Begins a new transaction.
        """
        self._db.begin()

    def commit(self):
        """
        Commits the current transaction.
        """
        self._db.commit()

    def rollback(self):
        """
        Rolls back the current transaction.
        """
        self._db.rollback()

    class Config:
        """
        A class representing the configuration for the SQLRepository class.

        Attributes:
        -----------
        database: type[SQLDatabase]
            The type of the SQL database to use.
        """

        database: type[SQLDatabase]
