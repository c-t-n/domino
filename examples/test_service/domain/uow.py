from abc import abstractmethod
from domino.domain.uow.uow import AbstractUnitOfWork

from test_service.domain.repositories import AbstractTimeCapsuleRepository

class TimeCapsuleUnitOfWork(AbstractUnitOfWork):
    @property
    @abstractmethod
    def time_capsule_repository(self) -> AbstractTimeCapsuleRepository:
        return NotImplemented