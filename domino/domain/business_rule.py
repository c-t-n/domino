from abc import ABC, abstractmethod
from typing import Any

from domino.base.baseclass import DominoBaseClass
from domino.exceptions import BusinessRuleViolation


class BusinessRule(DominoBaseClass, ABC):
    """
    A base class for business rules.
    """

    rule_id: int | str
    error_message: str

    @abstractmethod
    def rule(self, *args, **kwargs) -> bool:
        return NotImplemented

    def __init__(self, *args: Any, **kwds: Any):
        if not self.rule(*args, **kwds):
            raise BusinessRuleViolation(self.error_message, id=self.rule_id)
