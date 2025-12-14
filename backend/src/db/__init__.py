from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from ..settings import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()


def get_db():
    """DBセッションのFastAPI依存性。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
