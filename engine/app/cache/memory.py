# In-process L1 cache — TTL-aware, LRU-capped. Lost on restart by design (no persistence).
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple

_DEFAULT_MAXSIZE = 2000


class InMemoryTTLCache:
    """Sync dict-based cache. Not a CacheBackend itself — wrapped by LayeredCacheBackend."""

    def __init__(self, maxsize: int = _DEFAULT_MAXSIZE):
        self._maxsize = maxsize
        self._store: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= time.monotonic():
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        if key in self._store:
            del self._store[key]
        elif len(self._store) >= self._maxsize:
            self._store.popitem(last=False)  # evict least recently used
        self._store[key] = (time.monotonic() + ttl_seconds, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
