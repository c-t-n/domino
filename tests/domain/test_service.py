import pytest
from domino.domain.services.service import Service
from domino.domain.uow.uow import AbstractUnitOfWork

class DummyUnitOfWork(AbstractUnitOfWork):
    pass


class TestService:
    def test_can_initialize(self):
        Service(unit_of_work=DummyUnitOfWork())

    def test_raise_an_exception_when_unit_of_work_contains_bad_repositories(self):
        with pytest.raises(Exception):
            Service(unit_of_work=DummyUnitOfWork(repo_one=None)) # type: ignore