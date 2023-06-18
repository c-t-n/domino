from domino.base.baseclass import DominoBaseClass
from domino.domain.repositories.base import AbstractRepository
from domino.exceptions.unit_of_work import NotARepository


class AbstractUnitOfWork(DominoBaseClass):
    def __init__(self, **repositories: AbstractRepository) -> None:
        super().__init__()
        self.__repositories = list[str]()

        for repo_name, repo in repositories.items():
            if not issubclass(repo.__class__, AbstractRepository):
                raise NotARepository()
        
            setattr(self, repo_name, repo()) # type: ignore
        self._log.debug("UnitOfWork initialized")
    
    def __start_transaction(self):
        for repository in self.__repositories:
            repo = self.__getattribute__(repository)
            repo.start_transaction(self)

    def __commit_transaction(self):
        for repository in self.__repositories:
            repo = self.__getattribute__(repository)
            repo.commit_transaction(self)

    def __rollback_transaction(self):
        for repository in self.__repositories:
            repo = self.__getattribute__(repository)
            repo.rollback_transaction(self)


    def __enter__(self):
        self.__start_transaction()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.__rollback_transaction()
            self._log.error("Something went wrong, transaction rollbacked")
        else:
            self.__commit_transaction()