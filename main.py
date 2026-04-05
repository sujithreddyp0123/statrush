"""
FIX 8  — Security middleware registered.
FIX 11 — Structured logging configured at startup.
"""
import logging, time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager

from core.config import get_settings
from core.database import engine, Base, SessionFactory
from core.logging_cfg import setup_logging
from ml.registry import load_all as load_models
from routers import predictions, players, props, analytics, auth
from seed import seed_if_empty
from services.scheduler import start as scheduler_start, stop as scheduler_stop

cfg = get_settings()
setup_logging()
log = logging.getLogger("statrush.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run column migrations before create_all (safe on both SQLite and Postgres)
    from sqlalchemy import text
    async with engine.begin() as conn:
        migrations = [
            "ALTER TABLE prop_lines ADD COLUMN IF NOT EXISTS bookmaker VARCHAR(60)",
            "ALTER TABLE prop_lines ADD COLUMN IF NOT EXISTS is_best_line BOOLEAN DEFAULT FALSE",
            "ALTER TABLE prop_lines ADD COLUMN IF NOT EXISTS game_id VARCHAR(120)",
            "ALTER TABLE prop_lines ADD COLUMN IF NOT EXISTS game_time_utc VARCHAR(40)",
            "ALTER TABLE prop_lines ADD COLUMN IF NOT EXISTS over_odds INTEGER",
            "ALTER TABLE prop_lines ADD COLUMN IF NOT EXISTS under_odds INTEGER",
        ]
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed data
    async with SessionFactory() as db:
        await seed_if_empty(db)

    # Auto-train if no models exist
    model_dir = Path("./artifacts/models")
    model_dir.mkdir(parents=True, exist_ok=True)
    if not any(model_dir.glob("*.pkl")):
        log.info("No trained models found — running initial training...")
        try:
            from ml.trainer import train_all_stats
            async with SessionFactory() as train_db:
                await train_all_stats(train_db)
            load_models()
            log.info("Initial training complete")
        except Exception as e:
            log.warning(f"Initial training failed: {e} — will use heuristic fallback")
    else:
        load_models()

    # Fetch tonight + tomorrow prop lines
    log.info("Fetching tonight and tomorrow prop lines...")
    try:
        from services.ingestion import fetch_and_store_todays_props
        async with SessionFactory() as props_db:
            count = await fetch_and_store_todays_props(props_db)
            log.info(f"Fetched {count} live prop lines")
    except Exception as e:
        log.warning(f"Live props fetch failed: {e}")

    live_keys = []
    if cfg.BALLDONTLIE_API_KEY:
        live_keys.append("BallDontLie")
    if cfg.ODDS_API_KEY:
        live_keys.append("OddsAPI")
    if live_keys:
        log.info(f"Live API keys detected: {', '.join(live_keys)}")
    log.info(f"StatRush API ready [env={cfg.ENV} model={cfg.MODEL_VERSION}]")
    scheduler_start()
    yield
    scheduler_stop()
    await engine.dispose()


app = FastAPI(
    title="StatRush API",
    version="4.0.0",
    lifespan=lifespan,
    docs_url="/docs" if cfg.ENV != "prod" else None,
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://statrush.app",
        "https://statrush.vercel.app",
        "https://statrush-1yc99o347-sujithreddyp0123s-projects.vercel.app",
        "https://*.vercel.app",
        "https://statrush-api.onrender.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0  = time.monotonic()
    res = await call_next(request)
    ms  = round((time.monotonic() - t0) * 1000, 1)
    log.info(
        f"{request.method} {request.url.path} -> {res.status_code}",
        extra={"latency_ms": ms},
    )
    res.headers["X-Response-Time"] = f"{ms}ms"
    return res

# Routers
app.include_router(auth.router)
app.include_router(players.router)
app.include_router(props.router)
app.include_router(predictions.router)
app.include_router(analytics.router)

@app.get("/")
async def root():
    return {"status": "StatRush API running", "docs": "/docs"}

@app.get("/health")
async def health():
    return {"status": "ok", "env": cfg.ENV, "model": cfg.MODEL_VERSION}
