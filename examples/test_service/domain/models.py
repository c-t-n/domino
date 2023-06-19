from domino.domain.models.pydantic import DomainModel

class TimeCapsuleModel(DomainModel):
    user_id: int
    motivations: str
    objectives: str
    adaptations: str
    

class TimeCapsuleCreateModel(DomainModel):
    motivations: str
    objectives: str
    adaptations: str
