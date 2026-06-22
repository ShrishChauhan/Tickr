# SQLAlchemy ORM models — TODO(Phase 2): define cache/normalized tables fully
# TODO(Phase 2): add tables for cached fundamentals, filing refs, AI analysis results
from sqlalchemy import Column, String, Text, Integer, DateTime, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class CacheEntry(Base):
    """Generic key-value cache table with TTL tracking."""
    __tablename__ = "cache_entries"

    key = Column(String(512), primary_key=True)
    value = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
