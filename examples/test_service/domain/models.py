from domino.domain.models.pydantic import DomainModel

class TimeCapsuleModel(DomainModel):
    motivations: str
    objectives: str
    