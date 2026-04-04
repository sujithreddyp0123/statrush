"""
FIX 3 — /v1/players returns real data from DB (seeded from ingestion).
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from core.database import get_db
from core.redis_client import cache_get, cache_set
from models.orm import Player, GameLog
from core.config import get_settings

cfg = get_settings()
log = logging.getLogger("statrush.router.players")
router = APIRouter(prefix="/v1/players", tags=["players"])


class PlayerOut(BaseModel):
    id:       int
    name:     str
    team:     str | None
    position: str | None
    sport:    str
    active:   bool
    class Config: from_attributes = True


@router.get("/", response_model=list[PlayerOut])
async def list_players(db: AsyncSession = Depends(get_db)):
    cache_key = "sr:players:active"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        select(Player).where(Player.active == True).order_by(Player.name)
    )
    players = result.scalars().all()
    data = [PlayerOut.model_validate(p).model_dump() for p in players]
    await cache_set(cache_key, data, ttl=cfg.CACHE_TTL_PLAYERS)
    return data


@router.get("/{player_id}", response_model=PlayerOut)
async def get_player(player_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Player).where(Player.id == player_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Player not found")
    return p


@router.get("/{player_id}/logs")
async def get_game_logs(player_id: int, limit: int = 10,
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GameLog)
        .where(GameLog.player_id == player_id)
        .order_by(GameLog.game_date.desc())
        .limit(limit)
    )
    return result.scalars().all()
