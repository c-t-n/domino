from domino.domain.repositories import CreateRepositoryMixin, GetRepositoryMixin
from examples.test_service.domain.models import TimeCapsuleModel, TimeCapsuleCreateModel

from test_service.domain.models import TimeCapsuleModel

class AbstractTimeCapsuleRepository(
    GetRepositoryMixin[TimeCapsuleModel],
    CreateRepositoryMixin[TimeCapsuleModel, TimeCapsuleCreateModel]
):
    pass
