from typing import Any
from domino.domain.services import Service
from examples.test_service.domain.models import TimeCapsuleModel
from test_service.domain.uow import TimeCapsuleUnitOfWork
from test_service.domain.models import TimeCapsuleModel


class TimeCapsuleService(Service[TimeCapsuleUnitOfWork]):

    def write_time_capsule(self, user_id: int, time_capsule_data: dict) -> TimeCapsuleModel:
        payload = TimeCapsuleModel(user_id=user_id, **time_capsule_data)
        with self.unit_of_work:
            return self.unit_of_work.time_capsule_repository.create(payload)
