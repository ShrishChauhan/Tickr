# Static universe (index constituent) loading — extracted from routes.py
import json
from pathlib import Path
from typing import Dict, List

_UNIVERSES_DIR = Path(__file__).resolve().parent.parent / "data" / "universes"
_cache: Dict[str, List[dict]] = {}


class UnknownUniverseError(Exception):
    """Carries the requested key for HTTPException(404, detail=str(e))."""


def load_universe(key: str) -> List[dict]:
    if key not in _cache:
        path = _UNIVERSES_DIR / f"{key}.json"
        if not path.exists():
            raise UnknownUniverseError(
                f"Unknown universe '{key}'. Valid: {', '.join(known_universe_keys())}"
            )
        _cache[key] = json.loads(path.read_text(encoding="utf-8"))
    return _cache[key]


def known_universe_keys() -> List[str]:
    return sorted(p.stem for p in _UNIVERSES_DIR.glob("*.json"))
