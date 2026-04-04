"""
FIX 6 — Cache key now includes model_version + feature flag hash.
This ensures stale predictions are never served after a model update.
"""
import json, logging
import redis.asyncio as aioredis
from typing import Any, Optional
from core.config import get_settings, feature_flag_hash

cfg = get_settings()
log = logging.getLogger("statrush.cache")
_pool: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = await aioredis.from_url(
            cfg.REDIS_URL, encoding="utf-8",
            decode_responses=True, max_connections=50,
        )
    return _pool


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
        val = await r.get(key)
        if val:
            log.debug(f"cache hit: {key[:60]}")
            return json.loads(val)
        return None
    except Exception as e:
        log.warning(f"cache_get failed: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int):
    try:
        r = await get_redis()
        await r.setex(key, ttl, json.dumps(value, default=str))
    except Exception as e:
        log.warning(f"cache_set failed: {e}")


async def cache_delete_pattern(pattern: str):
    try:
        r = await get_redis()
        keys = await r.keys(pattern)
        if keys:
            await r.delete(*keys)
    except Exception as e:
        log.warning(f"cache_delete_pattern failed: {e}")


async def rate_limit(identifier: str, limit: int = 100, window: int = 60) -> bool:
    try:
        r = await get_redis()
        key = f"sr:rl:{identifier}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, window)
        return count <= limit
    except Exception:
        return True  # Fail open on Redis errors
