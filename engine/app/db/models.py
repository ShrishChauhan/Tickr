# SQLAlchemy ORM models
from sqlalchemy import Column, String, Integer, DateTime, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(512), nullable=False, unique=True)   # "edgar:fundamentals:AAPL:annual:5"
    data_type = Column(String(64), nullable=False)                 # "company" | "fundamentals" | "filings" | "analysis"
    ticker = Column(String(20), nullable=False)                    # denormalized for per-ticker invalidation
    source = Column(String(32), nullable=False)                    # "edgar" | "yfinance"
    payload = Column(JSON, nullable=False)                         # serialized response
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_cache_entries_expires_at", "expires_at"),
        Index("ix_cache_entries_ticker_dtype", "ticker", "data_type"),
    )
