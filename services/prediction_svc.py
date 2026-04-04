"""
FIX 2  — ML-first. XGB+LGBM produce all numbers. LLM produces explanation only.
FIX 7  — _persist_prediction opens its OWN session. Never shares caller's session.
FIX 9  — LLM runs as asyncio.create_task (non-blocking). ML result returned immediately.
FIX 11 — Structured logging on every stage.
"""
import asyncio, logging, time
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.orm import Prediction, Player, PropLine, StatType, GameLog
from ml.inference import run_inference
from llm.explainer import explain_prediction
from core.redis_client import cache_get, cache_set, make_pred_key
from core.config import get_settings
from core.database import SessionFactory

cfg = get_settings()
log = logging.getLogger("statrush.prediction_svc")


async def get_or_create_prediction(
    player_id:           int,
    stat_type:           StatType,
    line:                float,
    game_date:           datetime,
    user_id:             int | None,
    db:                  AsyncSession,
    include_explanation: bool = True,
) -> dict:
    t0 = time.monotonic()

    cache_key = make_pred_key(player_id, stat_type.value, line, str(game_date.date()))
    cached = await cache_get(cache_key)
    if cached:
        log.info("prediction cache hit",
                 extra={"player_id": player_id, "stat_type": stat_type.value,
                        "latency_ms": round((time.monotonic()-t0)*1000, 1)})
        return cached

    # Step 1 — Fetch recent game logs
    logs_result = await db.execute(
        select(GameLog)
        .where(GameLog.player_id == player_id)
        .order_by(GameLog.game_date.desc())
        .limit(15)
    )
    logs = logs_result.scalars().all()

    # Step 2 — Get juice for implied prob
    over_juice = await _get_latest_juice(player_id, stat_type, db)

    # Step 3 — ML inference (handles all fallbacks internally)
    ml_result = run_inference(logs, stat_type, line, over_juice)

    # Step 4 — Fetch player name
    p_res = await db.execute(select(Player).where(Player.id == player_id))
    player = p_res.scalar_one_or_none()
    player_name = player.name if player else f"Player #{player_id}"

    # Step 5 — Assemble result
    result = {
        "player_id":         player_id,
        "player_name":       player_name,
        "stat_type":         stat_type.value,
        "line":              line,
        "prediction":        ml_result["prediction"],
        "probability":       ml_result["probability"],
        "confidence":        ml_result["confidence"],
        "regression":        ml_result["regression"],
        "implied_prob":      ml_result["implied_prob"],
        "edge_pct":          ml_result["edge_pct"],
        "edge_label":        ml_result["edge_label"],
        "stat_edge":         ml_result["stat_edge"],
        "is_high_value":     ml_result["is_high_value"],
        "kelly_fraction":    ml_result["kelly_fraction"],
        "signals":           [],
        "summary":           "",
        "explanation_ready": False,
        "cache_key":         cache_key,
        "model_version":     cfg.MODEL_VERSION,
        "feature_snapshot":  ml_result["feature_snapshot"],
    }

    # Step 6 — Explanation
    if include_explanation:
        asyncio.create_task(
            _run_and_patch_explanation(
                result=result, cache_key=cache_key, player_name=player_name,
                stat_type=stat_type, line=line, ml_result=ml_result,
                game_date=game_date,
            )
        )
    else:
        from llm.explainer import _fallback_explanation
        expl = _fallback_explanation(
            player_name, stat_type.value,
            ml_result["prediction"], ml_result["probability"], ml_result["edge_pct"]
        )
        result["signals"]           = expl["signals"]
        result["summary"]           = expl["summary"]
        result["explanation_ready"] = True
        await cache_set(cache_key, result, ttl=cfg.CACHE_TTL_PRED)
        asyncio.create_task(_persist_prediction(result, game_date))

    ms = round((time.monotonic() - t0) * 1000, 1)
    log.info("prediction generated",
             extra={"player_id": player_id, "stat_type": stat_type.value,
                    "edge_pct": ml_result["edge_pct"],
                    "model_version": cfg.MODEL_VERSION, "latency_ms": ms})
    return result


async def _run_and_patch_explanation(
    result, cache_key, player_name, stat_type, line, ml_result, game_date,
):
    try:
        expl = await explain_prediction(
            player_name  = player_name,
            stat_type    = stat_type.value,
            line         = line,
            prediction   = ml_result["prediction"],
            probability  = ml_result["probability"],
            edge_pct     = ml_result["edge_pct"],
            recent_stats = list(ml_result["feature_snapshot"].values()),
        )
        result["signals"]           = expl["signals"]
        result["summary"]           = expl["summary"]
        result["explanation_ready"] = True
    except Exception as e:
        log.warning(f"LLM explanation failed, using fallback: {e}")
        from llm.explainer import _fallback_explanation
        expl = _fallback_explanation(
            player_name, stat_type.value,
            ml_result["prediction"], ml_result["probability"], ml_result["edge_pct"]
        )
        result["signals"]           = expl["signals"]
        result["summary"]           = expl["summary"]
        result["explanation_ready"] = True

    await cache_set(cache_key, result, ttl=cfg.CACHE_TTL_PRED)
    await _persist_prediction(result, game_date)


async def _get_latest_juice(player_id: int, stat_type: StatType,
                             db: AsyncSession) -> int:
    result = await db.execute(
        select(PropLine)
        .where(PropLine.player_id == player_id, PropLine.stat_type == stat_type)
        .order_by(PropLine.game_date.desc())
        .limit(1)
    )
    pl = result.scalar_one_or_none()
    return int(pl.over_odds) if pl and pl.over_odds else -110


async def _persist_prediction(result: dict, game_date: datetime):
    """FIX 7: Always opens a fresh session. Safe to call from background tasks."""
    try:
        async with SessionFactory() as session:
            pred = Prediction(
                player_id     = result["player_id"],
                stat_type     = StatType(result["stat_type"]),
                line          = result["line"],
                prediction    = result["prediction"],
                probability   = result["probability"],
                edge_pct      = result["edge_pct"],
                model_version = result["model_version"],
                explanation   = result.get("summary", ""),
            )
            session.add(pred)
            await session.commit()
    except Exception as e:
        log.error(f"_persist_prediction failed: {e}", exc_info=True)
