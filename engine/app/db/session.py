# SQLAlchemy async session factory — TODO(Phase 2): switch to async engine when wiring cache
# Requires DATABASE_URL in .env before any DB operations
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..config import settings

# Will raise at import time if DATABASE_URL is empty and code actually tries to connect
engine = create_engine(settings.DATABASE_URL) if settings.DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine) if engine else None
