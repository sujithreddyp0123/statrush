"""
Props router — GET /v1/props and GET /v1/props/upcoming
"""
import logging
from datetime import datetime, timedelta, timezone
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


class BookLine(BaseModel):
    bookmaker:  str | None
    line:       float
    over_odds:  float | None
    under_odds: float | None
    is_best:    bool


class PropOut(BaseModel):
    id:            int
    player_id:     int
    stat_type:     StatType
    line:          float
    over_odds:     float | None
    under_odds:    float | None
    actual_value:  float | None
    bookmaker:     str | None
    is_best_line:  bool | None
    game_id:       str | None
    game_time_utc: str | None
    all_books:     list[BookLine] = []
    class Config: from_attributes = True


@router.get("/upcoming")
async def upcoming_games(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PropLine)
        .where(PropLine.game_time_utc != None)
        .where(PropLine.is_best_line == True)
        .order_by(PropLine.game_time_utc.asc())
    )
    props = result.scalars().all()

    seen  = set()
    games = []
    for p in props:
        key = f"{p.player_id}_{p.stat_type}"
        if key not in seen:
            seen.add(key)
            games.append({
                "player_id":     p.player_id,
                "stat_type":     p.stat_type,
                "line":          p.line,
                "bookmaker":     p.bookmaker,
                "game_time_utc": p.game_time_utc,
                "game_id":       p.game_id,
            })
    return games


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
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="No props found for today")

    # Group by stat_type to attach all_books
    from collections import defaultdict
    groups: dict[str, list[PropLine]] = defaultdict(list)
    for r in rows:
        groups[r.stat_type].append(r)

    data = []
    for _, group in groups.items():
        # Real (bookmaker-tagged) lines take priority for display
        real = [p for p in group if p.bookmaker]
        display_group = real if real else group
        # Deduplicate by bookmaker — keep highest line per book
        seen_books: dict[str, PropLine] = {}
        for p in display_group:
            bk = p.bookmaker or ""
            if bk not in seen_books or p.line > seen_books[bk].line:
                seen_books[bk] = p
        unique = sorted(seen_books.values(), key=lambda x: x.line, reverse=True)
        best = unique[0]  # highest line after dedup
        out = PropOut.model_validate(best)
        out.all_books = [
            BookLine(
                bookmaker=p.bookmaker,
                line=p.line,
                over_odds=p.over_odds,
                under_odds=p.under_odds,
                is_best=(p.id == best.id),
            )
            for p in unique
        ]
        data.append(out.model_dump())

    await cache_set(cache_key, data, ttl=600)
    return data
