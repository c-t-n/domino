from abc import abstractmethod
from domino.base.baseclass import DominoBaseClass


class AbstractUnitOfWork(DominoBaseClass):
    @abstractmethod
    def __init__(self):
        raise NotImplementedError

    # Context Management
    def __enter__(self):
        self.begin()

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.rollback()
            return False
        else:
            self.commit()
            return True

    # UOW Transaction Management
    @abstractmethod
    def commit(self):
        """
        Commits the current transaction for all repositories in the unit of work.
        """
        raise NotImplementedError

    @abstractmethod
    def rollback(self):
        """
        Rolls back the current transaction for all repositories in the unit of work.
        """
        raise NotImplementedError

    @abstractmethod
    def begin(self):
        """
        Begins a new transaction for all repositories in the unit of work.
        """
        raise NotImplementedError
