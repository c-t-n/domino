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
