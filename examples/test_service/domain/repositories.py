from typing import Any
from domino.domain.repositories import CreateRepositoryMixin, GetRepositoryMixin
from examples.test_service.domain.models import TimeCapsuleModel

from test_service.domain.models import TimeCapsuleModel

class AbstractTimeCapsuleRepository(
    GetRepositoryMixin[TimeCapsuleModel],
    CreateRepositoryMixin[TimeCapsuleModel, TimeCapsuleModel]
):
    pass
