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
        return

    def rollback(self):
        return

    def begin(self):
        return
