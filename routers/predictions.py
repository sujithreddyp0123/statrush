"""
FIX 9  — include_explanation read from request body
FIX 10 — single clean endpoint; frontend calls this and only this
FIX 11 — request-level logging
"""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from core.database import get_db
from core.redis_client import rate_limit
from models.orm import StatType
from services.prediction_svc import get_or_create_prediction

log = logging.getLogger("statrush.router.predictions")
router = APIRouter(prefix="/v1/predictions", tags=["predictions"])


class PredictionRequest(BaseModel):
    player_id:           int
    stat_type:           StatType
    line:                float
    game_date:           Optional[datetime] = None
    include_explanation: bool = True


class PredictionResponse(BaseModel):
    player_id:         int
    player_name:       str
    stat_type:         str
    line:              float
    prediction:        str
    probability:       float
    confidence:        Optional[int]   = None
    regression:        Optional[float] = None
    implied_prob:      Optional[float] = None
    edge_pct:          float
    is_high_value:     Optional[bool]  = None
    kelly_fraction:    Optional[float] = None
    signals:           Optional[list]  = None
    summary:           Optional[str]   = None
    explanation_ready: Optional[bool]  = None
    cache_key:         Optional[str]   = None
    model_version:     Optional[str]   = None

    class Config:
        extra = "allow"


@router.post("/", response_model=PredictionResponse)
async def predict(
    req: PredictionRequest,
    db:  AsyncSession = Depends(get_db),
):
    if not await rate_limit("anon", limit=120, window=60):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    log.info("prediction request",
             extra={"player_id": req.player_id, "stat_type": req.stat_type.value})

    try:
        result = await get_or_create_prediction(
            player_id           = req.player_id,
            stat_type           = req.stat_type,
            line                = req.line,
            game_date           = req.game_date or datetime.now(timezone.utc),
            user_id             = None,
            db                  = db,
            include_explanation = req.include_explanation,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.error(f"Prediction endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/top")
async def top_picks(
    min_edge:  float              = Query(default=3.0),
    stat_type: Optional[StatType] = None,
    limit:     int                = Query(default=10, le=50),
    db:        AsyncSession       = Depends(get_db),
):
    from sqlalchemy import select
    from models.orm import Prediction

    q = select(Prediction).where(
        Prediction.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
        Prediction.edge_pct   >= min_edge,
    )
    if stat_type:
        q = q.where(Prediction.stat_type == stat_type)
    q = q.order_by(Prediction.edge_pct.desc()).limit(limit)

    result = await db.execute(q)
    return result.scalars().all()
