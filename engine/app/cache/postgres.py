# PostgreSQL TTL cache backend — sync SQLAlchemy wrapped in run_in_executor (same pattern as adapters)
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from .base import CacheBackend
from ..db.models import CacheEntry
from ..db.session import SessionLocal

logger = logging.getLogger(__name__)


class PostgresCacheBackend(CacheBackend):

    async def get(self, key: str) -> Optional[Any]:
        if not SessionLocal:
            return None
        try:
            return await asyncio.get_running_loop().run_in_executor(None, self._get_sync, key)
        except Exception:
            logger.warning("Cache get failed: %s", key, exc_info=True)
            return None

    def _get_sync(self, key: str) -> Optional[Any]:
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            row = (
                session.query(CacheEntry)
                .filter(CacheEntry.cache_key == key, CacheEntry.expires_at > now)
                .first()
            )
            payload = row.payload if row is not None else None
        if payload is None:
            logger.debug("CACHE MISS: %s", key)
        else:
            logger.debug("CACHE HIT: %s", key)
        return payload

    async def get_with_ttl(self, key: str) -> Optional[tuple[Any, int]]:
        """Like get(), but also returns remaining TTL in seconds. Used by LayeredCacheBackend
        to repopulate L1 with the same expiry L2 already has, rather than a guessed one."""
        if not SessionLocal:
            return None
        try:
            return await asyncio.get_running_loop().run_in_executor(None, self._get_with_ttl_sync, key)
        except Exception:
            logger.warning("Cache get_with_ttl failed: %s", key, exc_info=True)
            return None

    def _get_with_ttl_sync(self, key: str) -> Optional[tuple[Any, int]]:
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            row = (
                session.query(CacheEntry)
                .filter(CacheEntry.cache_key == key, CacheEntry.expires_at > now)
                .first()
            )
            if row is None:
                return None
            remaining = max(1, int((row.expires_at - now).total_seconds()))
            return row.payload, remaining

    async def get_with_ttl(self, key: str) -> Optional[tuple[Any, int]]:
        """Like get(), but also returns remaining TTL in seconds. Used by LayeredCacheBackend
        to repopulate L1 with the same expiry L2 already has, rather than a guessed one."""
        if not SessionLocal:
            return None
        try:
            return await asyncio.get_running_loop().run_in_executor(None, self._get_with_ttl_sync, key)
        except Exception:
            logger.warning("Cache get_with_ttl failed: %s", key, exc_info=True)
            return None

    def _get_with_ttl_sync(self, key: str) -> Optional[tuple[Any, int]]:
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            row = (
                session.query(CacheEntry)
                .filter(CacheEntry.cache_key == key, CacheEntry.expires_at > now)
                .first()
            )
            if row is None:
                return None
            remaining = max(1, int((row.expires_at - now).total_seconds()))
            return row.payload, remaining

    async def set(self, key: str, value: Any, ttl_seconds: int, *,
                  data_type: str = "", ticker: str = "", source: str = "") -> None:
        if not SessionLocal:
            return
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, self._set_sync, key, value, ttl_seconds, data_type, ticker, source
            )
        except Exception:
            logger.warning("Cache set failed: %s", key, exc_info=True)

    def _set_sync(self, key: str, value: Any, ttl_seconds: int,
                  data_type: str, ticker: str, source: str) -> None:
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        stmt = pg_insert(CacheEntry).values(
            cache_key=key,
            data_type=data_type,
            ticker=ticker,
            source=source,
            payload=value,
            expires_at=expires,
        ).on_conflict_do_update(
            index_elements=["cache_key"],
            set_=dict(
                payload=value,
                expires_at=expires,
                data_type=data_type,
                ticker=ticker,
                source=source,
            ),
        )
        with SessionLocal() as session:
            session.execute(stmt)
            session.commit()

    async def delete(self, key: str) -> None:
        if not SessionLocal:
            return
        try:
            await asyncio.get_running_loop().run_in_executor(None, self._delete_sync, key)
        except Exception:
            logger.warning("Cache delete failed: %s", key, exc_info=True)

    def _delete_sync(self, key: str) -> None:
        with SessionLocal() as session:
            session.query(CacheEntry).filter(CacheEntry.cache_key == key).delete()
            session.commit()
