class DominoException(Exception):
    pass


# Repositories exceptions
class PrimaryKeyPropertyNotDefined(DominoException):
    pass


class ItemNotFound(DominoException):
    pass


# Unit of Work exceptions
class NotARepository(DominoException):
    pass


class BusinessRuleViolation(DominoException):
    def __init__(self, message: str, id: int | str):
        self.id = id
        self.message = message
        super().__init__(f"{message} (id={id})")

    def to_json(self):
        return {"id": self.id, "message": self.message}
