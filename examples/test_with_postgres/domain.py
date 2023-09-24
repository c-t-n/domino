from datetime import datetime
from domino.domain.models.pydantic import Entity, DTO
from domino.domain.repositories import AbstractCRUDRepository
from domino.domain.services import Service
from domino.domain.uow import UnitOfWork


## Event Models
class Event(Entity):
    id: int
    title: str
    description: str
    date: datetime
    duration_in_min: int
    is_active: bool = False


class EventCreate(DTO):
    title: str
    description: str
    date: datetime
    duration_in_min: int


class EventUpdate(DTO):
    title: str | None = None
    description: str | None = None
    date: datetime | None = None
    duration_in_min: int | None = None
    is_active: bool | None = None


class AbstractEventRepository(AbstractCRUDRepository[Event, EventCreate, EventUpdate]):
    pass


## Abstract UnitOfWork
class AbstractEventUnitOfWork(UnitOfWork):
    event_repository: AbstractEventRepository


class EventsService(Service[AbstractEventUnitOfWork]):
    def create_event(self, data: EventCreate) -> Event:
        with self.unit_of_work as uow:
            event = uow.event_repository.create(data)

        return event

    def update_event(self, id: int, data: EventUpdate) -> Event:
        with self.unit_of_work as uow:
            event = uow.event_repository.get(id)
            if event.date < datetime.utcnow():
                raise Exception("Can't update an already started event")

            event = uow.event_repository.update(id, data)

        return event

    def delete_event(self, id: int) -> None:
        with self.unit_of_work as uow:
            uow.event_repository.delete(id)
