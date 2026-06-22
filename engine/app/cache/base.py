# Abstract cache interface — TODO(Phase 2): implement PostgreSQL-backed TTL cache
from abc import ABC, abstractmethod
from typing import Any, Optional


class CacheBackend(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Return cached value or None if missing/expired."""
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store value with TTL. Overwrites existing entry."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Explicitly invalidate a cache entry."""
        ...
