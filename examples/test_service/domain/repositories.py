from domino.domain.repositories.base import CreateRepositoryMixin, GetRepositoryMixin

from test_service.domain.models import TimeCapsuleModel

class AbstractTimeCapsuleRepository(
    GetRepositoryMixin[TimeCapsuleModel],
    CreateRepositoryMixin[TimeCapsuleModel],
):
    pass