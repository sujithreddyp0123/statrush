from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])


@router.get("/health")
async def analytics_health():
    return {"status": "ok"}


@router.post("/train")
async def trigger_training(db: AsyncSession = Depends(get_db)):
    from ml.trainer import train_all_stats
    from ml.registry import load_all
    results = await train_all_stats(db)
    load_all()
    return {"status": "training complete", "results": results}
