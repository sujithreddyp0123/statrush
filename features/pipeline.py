"""
Feature engineering pipeline.
Builds ML feature vectors from GameLog history in the DB.
Returns a FeatureVector object with .array, .feature_map, .n_games.
"""
import numpy as np
import logging
from datetime import datetime
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.orm import GameLog, StatType

log = logging.getLogger("statrush.features")

FEATURE_COLUMNS = [
    "avg_5g", "avg_10g", "avg_season",
    "std_5g", "std_10g",
    "min_5g", "max_5g",
    "avg_home", "avg_away",
    "minutes_avg_5g",
    "games_over_line_5g", "games_over_line_10g",
    "days_rest",
]


@dataclass
class FeatureVector:
    array:       np.ndarray
    feature_map: dict
    n_games:     int


def _safe(arr, fn, default=0.0):
    return float(fn(arr)) if arr else default


def _build_from_logs(game_logs: list, stat_col: str, line: float) -> FeatureVector:
    vals = [getattr(g, stat_col) for g in game_logs if getattr(g, stat_col) is not None]
    mins = [g.minutes for g in game_logs if g.minutes is not None]
    home_vals = [getattr(g, stat_col) for g in game_logs
                 if g.home and getattr(g, stat_col) is not None]
    away_vals = [getattr(g, stat_col) for g in game_logs
                 if not g.home and getattr(g, stat_col) is not None]

    v5  = vals[:5]
    v10 = vals[:10]
    feat = {
        "avg_5g":              _safe(v5,   np.mean),
        "avg_10g":             _safe(v10,  np.mean),
        "avg_season":          _safe(vals, np.mean),
        "std_5g":              _safe(v5,   np.std),
        "std_10g":             _safe(v10,  np.std),
        "min_5g":              _safe(v5,   np.min),
        "max_5g":              _safe(v5,   np.max),
        "avg_home":            _safe(home_vals, np.mean),
        "avg_away":            _safe(away_vals, np.mean),
        "minutes_avg_5g":      _safe(mins[:5], np.mean),
        "games_over_line_5g":  sum(1 for v in v5  if v > line) / max(len(v5),  1),
        "games_over_line_10g": sum(1 for v in v10 if v > line) / max(len(v10), 1),
        "days_rest":           0.0,
    }
    arr = np.array([[feat[c] for c in FEATURE_COLUMNS]], dtype=np.float32)
    return FeatureVector(array=arr, feature_map=feat, n_games=len(vals))


async def build_features(
    player_id: int,
    stat_type: StatType,
    line: float,
    game_date: datetime,
    db: AsyncSession,
) -> FeatureVector:
    stat_col = stat_type.value
    result = await db.execute(
        select(GameLog)
        .where(
            GameLog.player_id == player_id,
            GameLog.game_date < game_date.date(),
        )
        .order_by(GameLog.game_date.desc())
        .limit(25)
    )
    logs = result.scalars().all()

    if not logs:
        log.warning(f"No game logs for player {player_id} — using zero features")
        feat = {c: 0.0 for c in FEATURE_COLUMNS}
        arr = np.zeros((1, len(FEATURE_COLUMNS)), dtype=np.float32)
        return FeatureVector(array=arr, feature_map=feat, n_games=0)

    return _build_from_logs(logs, stat_col, line)


# Sync version kept for trainer use
def build_features_from_row(game_logs: list, stat_col: str, line: float) -> dict:
    return _build_from_logs(game_logs, stat_col, line).feature_map
