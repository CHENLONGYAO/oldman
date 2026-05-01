"""
TTL-based cache with LRU eviction and decorator support.

Wraps expensive functions (analytics, ML inference, DB aggregations) so
repeated calls within the TTL window return cached results.

Per-user invalidation: cache keys can be tagged with user_id; when a session
or profile changes, the user's tagged entries are evicted.

Usage:
    @cached(ttl=60, tag_arg="user_id")
    def get_improvement_rate(user_id: str):
        ...

    invalidate_for_user(user_id)
"""
from __future__ import annotations
import functools
import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Set, Tuple


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    tags: Set[str] = field(default_factory=set)
    hits: int = 0


class TTLCache:
    """Thread-safe TTL cache with LRU eviction and tag-based invalidation."""

    def __init__(self, max_size: int = 1024):
        self.max_size = max_size
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return None
            if time.time() > entry.expires_at:
                del self._store[key]
                self._stats["misses"] += 1
                return None
            self._store.move_to_end(key)
            entry.hits += 1
            self._stats["hits"] += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: float,
            tags: Optional[Set[str]] = None) -> None:
        with self._lock:
            self._store[key] = CacheEntry(
                value=value,
                expires_at=time.time() + ttl,
                tags=tags or set(),
            )
            self._store.move_to_end(key)
            while len(self._store) > self.max_size:
                self._store.popitem(last=False)
                self._stats["evictions"] += 1

    def invalidate(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def invalidate_tag(self, tag: str) -> int:
        """Invalidate all entries with a given tag."""
        with self._lock:
            keys_to_remove = [
                k for k, v in self._store.items() if tag in v.tags
            ]
            for k in keys_to_remove:
                del self._store[k]
            return len(keys_to_remove)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> Dict:
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total if total > 0 else 0
            return {
                **self._stats,
                "size": len(self._store),
                "max_size": self.max_size,
                "hit_rate": hit_rate,
            }

    def cleanup_expired(self) -> int:
        """Remove expired entries. Call periodically."""
        with self._lock:
            now = time.time()
            expired = [k for k, v in self._store.items()
                       if v.expires_at < now]
            for k in expired:
                del self._store[k]
            return len(expired)


_GLOBAL_CACHE = TTLCache(max_size=2048)


def cached(ttl: float = 60.0,
            tag_arg: Optional[str] = None,
            key_fn: Optional[Callable] = None,
            cache: Optional[TTLCache] = None) -> Callable:
    """Decorator that caches function results.

    Args:
        ttl: time-to-live in seconds
        tag_arg: name of an argument to use as a tag (e.g., "user_id")
        key_fn: optional custom key function (args, kwargs) -> str
        cache: optional cache instance (defaults to global)
    """
    target_cache = cache or _GLOBAL_CACHE

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if key_fn:
                key = key_fn(args, kwargs)
            else:
                key = _make_key(fn, args, kwargs)

            cached_value = target_cache.get(key)
            if cached_value is not None:
                return cached_value

            result = fn(*args, **kwargs)

            tags = set()
            if tag_arg:
                if tag_arg in kwargs:
                    tags.add(f"{tag_arg}:{kwargs[tag_arg]}")
                elif args:
                    try:
                        import inspect
                        sig = inspect.signature(fn)
                        params = list(sig.parameters.keys())
                        idx = params.index(tag_arg)
                        if idx < len(args):
                            tags.add(f"{tag_arg}:{args[idx]}")
                    except (ValueError, IndexError):
                        pass

            target_cache.set(key, result, ttl=ttl, tags=tags)
            return result

        wrapper.cache_invalidate = lambda: target_cache.clear()
        wrapper._cache = target_cache
        return wrapper

    return decorator


def _make_key(fn: Callable, args: tuple, kwargs: dict) -> str:
    """Generate stable cache key from function + arguments."""
    parts = [fn.__module__, fn.__name__]
    try:
        parts.append(json.dumps(list(args), sort_keys=True, default=str))
        parts.append(json.dumps(kwargs, sort_keys=True, default=str))
    except (TypeError, ValueError):
        parts.append(repr(args))
        parts.append(repr(kwargs))

    key_str = "|".join(parts)
    return hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:32]


# ============================================================
# Convenience helpers
# ============================================================
def invalidate_for_user(user_id: str) -> int:
    """Evict all cache entries tagged with this user."""
    return _GLOBAL_CACHE.invalidate_tag(f"user_id:{user_id}")


def get_cache_stats() -> Dict:
    """Return current cache statistics."""
    return _GLOBAL_CACHE.stats()


def cleanup_cache() -> int:
    """Remove expired entries. Returns count cleared."""
    return _GLOBAL_CACHE.cleanup_expired()


def clear_all() -> None:
    """Wipe the entire cache."""
    _GLOBAL_CACHE.clear()


# ============================================================
# Common cached helpers (importable shortcuts)
# ============================================================
@cached(ttl=120, tag_arg="user_id")
def cached_improvement_rate(user_id: str, window_days: int = 30):
    """Cached version of analytics.calculate_improvement_rate."""
    from analytics import calculate_improvement_rate
    return calculate_improvement_rate(user_id, window_days)


@cached(ttl=300, tag_arg="user_id")
def cached_risk_score(user_id: str):
    """Cached version of ml_insights.calculate_risk_score."""
    from ml_insights import calculate_risk_score
    return calculate_risk_score(user_id)


@cached(ttl=180, tag_arg="user_id")
def cached_recommendations(user_id: str, top_k: int = 3):
    """Cached version of ml_insights.recommend_exercises."""
    from ml_insights import recommend_exercises
    return recommend_exercises(user_id, top_k)


@cached(ttl=600)
def cached_cohort_stats():
    """Cached aggregate cohort stats (rarely changes)."""
    from analytics import get_cohort_stats
    return get_cohort_stats()
