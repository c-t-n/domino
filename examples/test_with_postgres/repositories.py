from sqlalchemy import Column, Integer, String, DateTime, Boolean, desc
from sqlalchemy.orm import DeclarativeBase
from domino.exceptions import ItemNotFound
from domino.repositories.sql.sqlalchemy.database import SQLDatabase
from domino.repositories.sql.sqlalchemy.repository import SQLRepository
from examples.test_with_postgres.domain import (
    AbstractEventRepository,
    Event,
    EventCreate,
    EventUpdate,
)


class InMemoryDatabase(SQLDatabase):
    class Config:
        dsn = "sqlite://"


class Base(DeclarativeBase):
    pass


class EventsMapping(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    title = Column(String)
    description = Column(String)
    date = Column(DateTime)
    duration_in_min = Column(Integer)
    is_active = Column(Boolean, default=False)


class EventRepository(SQLRepository, AbstractEventRepository):
    def get(self, id: int) -> Event:
        data = self.session.get(EventsMapping, id)
        if data is None:
            raise ItemNotFound
        return Event.model_validate(data)

    def create(self, data: EventCreate) -> Event:
        event = EventsMapping(**data.model_dump())
        self.session.add(event)
        self.session.flush()
        self.session.refresh(event)
        return Event.model_validate(event)

    def update(self, id: int, data: EventUpdate) -> Event:
        obj = self.session.get(EventsMapping, id)
        self.session.query(EventsMapping).filter_by(id=id).update(**data.model_dump())
        self.session.refresh(obj)
        return Event.model_validate(obj)

    def list(self, filter_data: dict) -> tuple[int, list[Event]]:
        query = (
            self.session.query(EventsMapping)
            .filter_by(**filter_data)
            .order_by(desc("id"))
        )

        return (
            query.count(),
            [Event.model_validate(event) for event in query.all()],
        )

    def delete(self, id: int) -> None:
        self.session.query(EventsMapping).filter_by(id=id).delete()
