from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from time import time
from typing import Any, Callable


@dataclass
class CacheEntry:
    value: Any
    created_at: float


_READ_CACHE: dict[str, CacheEntry] = {}
_CACHE_LOCK = RLock()
_MAX_CACHE_ENTRIES = 128


def get_cached_read_view(cache_key: str) -> Any | None:
    with _CACHE_LOCK:
        entry = _READ_CACHE.get(cache_key)
        if entry is None:
            return None
        return deepcopy(entry.value)


def set_cached_read_view(cache_key: str, value: Any) -> None:
    with _CACHE_LOCK:
        _READ_CACHE[cache_key] = CacheEntry(value=deepcopy(value), created_at=time())
        _prune_locked()


def get_or_build_cached_read_view(cache_key: str, builder: Callable[[], Any]) -> tuple[Any, bool]:
    cached = get_cached_read_view(cache_key)
    if cached is not None:
        return cached, True

    built = builder()
    if built is None:
        return None, False

    with _CACHE_LOCK:
        existing = _READ_CACHE.get(cache_key)
        if existing is not None:
            return deepcopy(existing.value), True
        _READ_CACHE[cache_key] = CacheEntry(value=deepcopy(built), created_at=time())
        _prune_locked()

    return deepcopy(built), False


def clear_read_cache() -> None:
    with _CACHE_LOCK:
        _READ_CACHE.clear()


def _prune_locked() -> None:
    if len(_READ_CACHE) <= _MAX_CACHE_ENTRIES:
        return

    overflow = len(_READ_CACHE) - _MAX_CACHE_ENTRIES
    oldest_keys = sorted(_READ_CACHE.items(), key=lambda item: item[1].created_at)[:overflow]
    for key, _entry in oldest_keys:
        _READ_CACHE.pop(key, None)
