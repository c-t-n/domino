class PostgresRepository:

    def __init__(self):
        self.__in_transaction = False

    @property
    def in_transaction(self):
        return self.__in_transaction

    def start_transaction(self):
        self.__in_transaction = True

    def commit_transaction(self):
        self.__in_transaction = False

    def rollback_transaction(self):
        self.__in_transaction = False
