from typing import Any
from domino.base.baseclass import DominoBaseClass
from domino.domain.repositories import AbstractRepository
from domino.exceptions import NotARepository


class AbstractUnitOfWork(DominoBaseClass):
    def __init__(self, **repositories: Any) -> None:
        super().__init__()
        self.__repositories = list[str]()

        for repo_name, repo in repositories.items():
            if not issubclass(repo, AbstractRepository):
                raise NotARepository()

            print(repo)
            self.__repositories.append(repo_name)
            setattr(self, repo_name, repo())  # type: ignore
        self._log.debug("UnitOfWork initialized")

    # UOW Transaction Management
    def __start_transaction(self):
        for repository in self.__repositories:
            repo = self.__getattribute__(repository)
            repo.start_transaction()

    def __commit_transaction(self):
        for repository in self.__repositories:
            repo = self.__getattribute__(repository)
            repo.commit_transaction()

    def __rollback_transaction(self):
        for repository in self.__repositories:
            repo = self.__getattribute__(repository)
            repo.rollback_transaction()

    # Context Management
    def __enter__(self):
        self.__start_transaction()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.__rollback_transaction()
            self._log.error("Something went wrong, transaction rollbacked")
        else:
            self.__commit_transaction()
