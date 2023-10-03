class DominoException(Exception):
    pass


class BusinessRuleViolation(DominoException):
    pass


# Repositories exceptions
class PrimaryKeyPropertyNotDefined(DominoException):
    pass


class ItemNotFound(DominoException):
    pass


# Unit of Work exceptions
class NotARepository(DominoException):
    pass
