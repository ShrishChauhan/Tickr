# SQLAlchemy session factory — sync engine, pool_pre_ping guards against stale remote connections
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..config import settings

# AUTOCOMMIT removes BEGIN/ROLLBACK round-trips: each cache op = 1 RTT (just the statement).
# All cache ops are single statements so no transactional atomicity is needed.
# pool_recycle=1800 drops idle connections before Neon's 5-min autosuspend can invalidate them.
# pool_pre_ping=False: postgres.py degrades gracefully on stale connections (catches and returns None).
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=False,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=5,
    execution_options={"isolation_level": "AUTOCOMMIT"},
) if settings.DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine) if engine else None
