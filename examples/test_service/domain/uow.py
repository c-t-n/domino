from domino.domain.uow import AbstractUnitOfWork

from test_service.domain.repositories import AbstractTimeCapsuleRepository


class TimeCapsuleUnitOfWork(AbstractUnitOfWork):
    time_capsule_repository: AbstractTimeCapsuleRepository
