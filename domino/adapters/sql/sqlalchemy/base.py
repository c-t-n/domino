from sqlalchemy import create_engine, Engine

from sqlalchemy.orm import Session, declared_attr


class DominoSQLBase:
    engine: Engine
    session: Session

    @declared_attr.directive
    def __tablename__(cls):
        return cls.__class__.__name__.lower()

    def __init__(self):
        DominoSQLBase.engine = create_engine(self.Config.dsn, echo=True)
        DominoSQLBase.session = Session(DominoSQLBase.engine)


    @property
    def has_transaction(self):
        return DominoSQLBase.session.in_transaction()

    def start_transaction(self):
        DominoSQLBase.session.begin()

    def commit_transaction(self):
        DominoSQLBase.session.commit()

    def rollback_transaction(self):
        DominoSQLBase.session.rollback()


    class Config:
        dsn: str
