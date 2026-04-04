"""
FIX 3 — GET /v1/props?player_id= returns today's prop lines from DB.
"""
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from core.database import get_db
from core.redis_client import cache_get, cache_set
from models.orm import PropLine, StatType
from core.config import get_settings

cfg = get_settings()
log = logging.getLogger("statrush.router.props")
router = APIRouter(prefix="/v1/props", tags=["props"])


class PropOut(BaseModel):
    id:           int
    player_id:    int
    stat_type:    StatType
    line:         float
    over_odds:    float | None
    under_odds:   float | None
    actual_value: float | None
    class Config: from_attributes = True


@router.get("/", response_model=list[PropOut])
async def get_props(
    player_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"sr:props:{player_id}:{datetime.utcnow().date()}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        select(PropLine).where(
            PropLine.player_id == player_id,
            PropLine.game_date >= datetime.utcnow().date() - timedelta(days=1),
        ).order_by(PropLine.game_date.desc())
    )
    props = result.scalars().all()
    if not props:
        raise HTTPException(status_code=404, detail="No props found for today")

    data = [PropOut.model_validate(p).model_dump() for p in props]
    await cache_set(cache_key, data, ttl=600)
    return data
