from typing import Generic, TypeVar

from domino.base.baseclass import DominoBaseClass
from domino.domain.uow import AbstractUnitOfWork

UOW = TypeVar("UOW", bound=AbstractUnitOfWork)


class Service(DominoBaseClass, Generic[UOW]):
    """
    Service is a base class for all services in the application.

    It provides a unit of work to be used in the service methods. It also
    provides a logger to be used in the service methods.
    """

    def __init__(self, unit_of_work: UOW) -> None:
        super().__init__()

        self.unit_of_work = unit_of_work
        self.log.debug("Service Initialized")
