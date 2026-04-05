"""
Admin router — internal maintenance endpoints.
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from datetime import datetime, timezone, timedelta

from core.database import get_db
from models.orm import PropLine

log = logging.getLogger("statrush.router.admin")
router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.post("/refresh-props")
async def refresh_props(db: AsyncSession = Depends(get_db)):
    """Delete recent prop lines and re-fetch from The Odds API."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).date()
    await db.execute(
        delete(PropLine).where(PropLine.game_date >= cutoff)
    )
    await db.commit()

    from services.ingestion import fetch_and_store_todays_props
    count = await fetch_and_store_todays_props(db)
    log.info(f"[admin] refresh-props inserted {count} lines")
    return {"status": "ok", "props_inserted": count}
