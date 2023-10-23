import pytest
from domino.domain.service import Service
from domino.domain.uow import AbstractUnitOfWork


class DummyUnitOfWork(AbstractUnitOfWork):
    def __init__(self):
        pass

    def commit(self):
        return

    def begin(self):
        return

    def rollback(self):
        return


class TestService:
    def test_can_initialize(self):
        Service(unit_of_work=DummyUnitOfWork())
