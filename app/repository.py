"""
In-memory repository.

Single responsibility: return raw place records.
Swap to SQLite/Postgres later by rewriting ONLY this file.
"""
import json
from pathlib import Path
from typing import List, Dict, Optional

_DATA_FILE = Path(__file__).parent / "data" / "places.json"
_cache: List[Dict] = []


def _load() -> List[Dict]:
    global _cache
    if not _cache:
        _cache = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    return _cache


def list_places() -> List[Dict]:
    return list(_load())


def get_place(place_id: str) -> Optional[Dict]:
    for p in _load():
        if p["id"] == place_id:
            return p
    return None
