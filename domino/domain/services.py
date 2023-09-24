from typing import TypeVar, Generic
from domino.base.baseclass import DominoBaseClass
from domino.domain.uow import UnitOfWork

UOW = TypeVar("UOW", bound=UnitOfWork)


class Service(DominoBaseClass, Generic[UOW]):
    def __init__(self, unit_of_work: UOW) -> None:
        super().__init__()

        self.unit_of_work = unit_of_work
        self._log.debug("Service Initialized")
