# SQLAlchemy session factory — sync engine, pool_pre_ping guards against stale remote connections
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True) if settings.DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine) if engine else None
