"""
Background scheduler — refreshes live prop lines every 60 minutes.
Uses APScheduler AsyncIOScheduler so it runs inside the existing event loop.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

log = logging.getLogger("statrush.scheduler")
scheduler = AsyncIOScheduler()


async def _refresh_props_job():
    log.info("[scheduler] Starting 60-min props refresh")
    try:
        from services.ingestion import fetch_and_store_todays_props
        from core.database import SessionFactory
        async with SessionFactory() as db:
            count = await fetch_and_store_todays_props(db)
        log.info(f"[scheduler] Props refresh done — {count} lines upserted")
    except Exception as e:
        log.warning(f"[scheduler] Props refresh failed: {e}")


scheduler.add_job(
    _refresh_props_job,
    trigger="interval",
    minutes=60,
    id="refresh_props",
    replace_existing=True,
)


def start():
    if not scheduler.running:
        scheduler.start()
        log.info("[scheduler] APScheduler started (refresh_props every 60 min)")


def stop():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("[scheduler] APScheduler stopped")
