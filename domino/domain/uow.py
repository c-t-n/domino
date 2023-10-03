from domino.base.baseclass import DominoBaseClass
from domino.domain.repositories import AbstractRepository


class UnitOfWork(DominoBaseClass):
    def __init__(self):
        self._in_transaction = False

    # Context Management
    def __enter__(self):
        self.begin()
        self._in_transaction = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._in_transaction = False
        if exc_type:
            self.rollback()
            raise exc_type(exc_value)
        else:
            self.commit()

    # UOW Transaction Management
    def commit(self):
        """
        Commits the current transaction for all repositories in the unit of work.
        """
        for item_name in dir(self):
            item = getattr(self, item_name)
            if isinstance(item, AbstractRepository):
                if item.in_transaction:
                    item.commit()
                continue

    def rollback(self):
        """
        Rolls back the current transaction for all repositories in the unit of work.
        """
        for item_name in dir(self):
            item = getattr(self, item_name)
            if isinstance(item, AbstractRepository):
                if item.in_transaction:
                    item.rollback()
                continue

    def begin(self):
        """
        Begins a new transaction for all repositories in the unit of work.
        """
        for item_name in dir(self):
            item = getattr(self, item_name)
            if isinstance(item, AbstractRepository):
                if not item.in_transaction:
                    item.begin()
                continue
