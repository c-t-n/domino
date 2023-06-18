from domino.domain.services.service import Service
from test_service.domain.uow import TimeCapsuleUnitOfWork
from test_service.domain.models import TimeCapsuleModel

class TimeCapsuleService(Service[TimeCapsuleUnitOfWork]):

    def write_time_capsule(self, user_id: int, time_capsule_data: dict):
        payload = TimeCapsuleModel(**time_capsule_data)
        with self.unit_of_work as uow:
            uow.time_capsule_repository.create(payload)