from sqlalchemy.orm import Session


class SQLRepository:
    """
    A class representing a SQL repository.

    Attributes:
    -----------
    _db: SQLDatabase
        The SQL database object.
    """

    def __init__(self, session: Session):
        self.session = session
