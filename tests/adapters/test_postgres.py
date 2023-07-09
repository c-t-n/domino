from domino.adapters.sql.sqlalchemy.base import DominoSQLBase
from sqlalchemy.orm import declarative_base

class SQLAdapter(DominoSQLBase):
    class Config:
        dsn = "sqlite:///:memory:"


Base = declarative_base(cls=SQLAdapter)

class TestSqlAdapter:
    def test_initialize_sql(self):
        adapter = SQLAdapter()
        adapter.start_transaction()

        assert adapter.has_transaction is True
