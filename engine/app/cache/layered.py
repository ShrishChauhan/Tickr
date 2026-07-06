# L1 (in-process) + L2 (Postgres) layered cache — same CacheBackend interface, transparent to callers.
import logging
from typing import Any, Optional

from .base import CacheBackend
from .memory import InMemoryTTLCache
from .postgres import PostgresCacheBackend

logger = logging.getLogger(__name__)


class LayeredCacheBackend(CacheBackend):

    def __init__(self, l2: Optional[CacheBackend] = None, l1_maxsize: int = 2000):
        self._l1 = InMemoryTTLCache(maxsize=l1_maxsize)
        self._l2 = l2 if l2 is not None else PostgresCacheBackend()

    async def get(self, key: str) -> Optional[Any]:
        value = self._l1.get(key)
        if value is not None:
            logger.debug("L1 HIT: %s", key)
            return value

        if isinstance(self._l2, PostgresCacheBackend):
            fetched = await self._l2.get_with_ttl(key)
            if fetched is None:
                return None
            value, remaining_ttl = fetched
            logger.debug("L1 MISS, L2 HIT: %s", key)
            self._l1.set(key, value, remaining_ttl)
            return value

        # Fallback for a CacheBackend without get_with_ttl (e.g. a test double) — can't
        # know remaining TTL, so skip L1 population rather than guessing an expiry.
        return await self._l2.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int, *,
                  data_type: str = "", ticker: str = "", source: str = "") -> None:
        self._l1.set(key, value, ttl_seconds)
        await self._l2.set(key, value, ttl_seconds, data_type=data_type, ticker=ticker, source=source)

    async def delete(self, key: str) -> None:
        self._l1.delete(key)
        await self._l2.delete(key)
