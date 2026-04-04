"""
FIX 6 — Cache key now includes model_version + feature flag hash.
This ensures stale predictions are never served after a model update.
Redis is optional — all operations fail silently when unavailable.
"""
import json, logging
import redis.asyncio as aioredis
from typing import Any, Optional
from core.config import get_settings, feature_flag_hash

cfg = get_settings()
log = logging.getLogger("statrush.cache")
_pool: Optional[aioredis.Redis] = None


async def get_redis() -> Optional[aioredis.Redis]:
    try:
        global _pool
        if _pool is None:
            redis_url = cfg.REDIS_URL
            if not redis_url:
                return None
            _pool = await aioredis.from_url(
                redis_url, encoding="utf-8",
                decode_responses=True, max_connections=50,
            )
        return _pool
    except Exception:
        return None


def make_pred_key(player_id: int, stat: str, line: float, date: str) -> str:
    """
    FIX 6: versioned cache key.
    Format: pred:{model_version}:{flag_hash}:{player_id}:{stat}:{line}:{date}
    Invalidates automatically when model version or feature flags change.
    """
    return (
        f"sr:pred:{cfg.MODEL_VERSION}:{feature_flag_hash()}"
        f":{player_id}:{stat}:{line}:{date}"
    )


def make_llm_key(player_id: int, stat: str, prediction: str, confidence: int) -> str:
    return f"sr:llm:{cfg.MODEL_VERSION}:{player_id}:{stat}:{prediction}:{confidence}"


async def cache_get(key: str) -> Optional[Any]:
    try:
        r = await get_redis()
        if r is None:
            return None
        val = await r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int):
    try:
        r = await get_redis()
        if r is None:
            return
        await r.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        return


async def cache_delete_pattern(pattern: str):
    try:
        r = await get_redis()
        if r is None:
            return
        keys = await r.keys(pattern)
        if keys:
            await r.delete(*keys)
    except Exception:
        return


async def rate_limit(identifier: str, limit: int = 100, window: int = 60) -> bool:
    return True
