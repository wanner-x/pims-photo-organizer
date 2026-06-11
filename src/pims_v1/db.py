from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.config import settings
from pims_v1.models.base import Base


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

__all__ = ["Base", "SessionLocal", "engine"]
