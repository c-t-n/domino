from domino.repositories.sql.sqlalchemy.database import SQLDatabase


class InMemoryDatabase(SQLDatabase):
    dsn = "sqlite:///:memory:"


class LocalDatabase(SQLDatabase):
    host = "localhost"
    port = 5432
    database = "domino"
    username = "domino"
    password = "domino"


class TestSQLDatabase:
    def test_dsn(self):
        assert InMemoryDatabase().computed_dsn == "sqlite:///:memory:"
        assert (
            LocalDatabase().computed_dsn
            == "postgresql://domino:domino@localhost:5432/domino"
        )
