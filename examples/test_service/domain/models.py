from domino.domain.models.pydantic import DomainModel, DTO

class TimeCapsuleModel(DomainModel):
    user_id: int
    motivations: str
    objectives: str
    adaptations: str
    

class TimeCapsuleCreateModel(DTO):
    motivations: str
    objectives: str
    adaptations: str
