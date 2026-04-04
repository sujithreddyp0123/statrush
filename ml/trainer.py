import numpy as np
import pandas as pd
import pickle
import logging
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, brier_score_loss
from xgboost import XGBClassifier, XGBRegressor
from lightgbm import LGBMClassifier

log = logging.getLogger("statrush.trainer")

FEATURE_COLUMNS = [
    "avg_5g", "avg_10g", "avg_season", "std_5g", "std_10g",
    "min_5g", "max_5g", "avg_home", "avg_away",
    "minutes_avg_5g", "games_over_line_5g", "games_over_line_10g",
    "days_rest", "is_b2b", "usage_rate", "opp_def_rank",
    "home_away", "team_pace", "opp_pace", "line_vs_avg5"
]

def build_feature_vector(logs, stat_col, line):
    vals = [getattr(g, stat_col, 0) or 0 for g in logs]
    if not vals:
        return None
    vals = [float(v) for v in vals]
    n = len(vals)
    avg5 = float(np.mean(vals[:5])) if n >= 5 else float(np.mean(vals))
    avg10 = float(np.mean(vals[:10])) if n >= 10 else float(np.mean(vals))
    avg_all = float(np.mean(vals))
    std5 = float(np.std(vals[:5])) if n >= 5 else (float(np.std(vals)) if n > 1 else 0.0)
    std10 = float(np.std(vals[:10])) if n >= 10 else (float(np.std(vals)) if n > 1 else 0.0)
    min5 = float(np.min(vals[:5])) if n >= 5 else float(np.min(vals))
    max5 = float(np.max(vals[:5])) if n >= 5 else float(np.max(vals))
    home_vals = [float(getattr(g, stat_col, 0) or 0) for g in logs if getattr(g, "home_away", "home") == "home"]
    away_vals = [float(getattr(g, stat_col, 0) or 0) for g in logs if getattr(g, "home_away", "home") == "away"]
    avg_home = float(np.mean(home_vals)) if home_vals else avg_all
    avg_away = float(np.mean(away_vals)) if away_vals else avg_all
    mins = [float(getattr(g, "minutes", 32) or 32) for g in logs[:5]]
    minutes_avg = float(np.mean(mins)) if mins else 32.0
    over5 = float(np.mean([1 if v > line else 0 for v in vals[:5]])) if n >= 5 else 0.5
    over10 = float(np.mean([1 if v > line else 0 for v in vals[:10]])) if n >= 10 else over5
    rest = float(getattr(logs[0], "rest_days", 2) or 2)
    b2b = float(bool(getattr(logs[0], "is_b2b", False)))
    usage = float(getattr(logs[0], "usage_rate", 28) or 28)
    opp_rank = float(getattr(logs[0], "opp_pts_allowed_rank", 15) or 15)
    home = 1.0 if getattr(logs[0], "home_away", "home") == "home" else 0.0
    t_pace = float(getattr(logs[0], "team_pace", 100) or 100)
    o_pace = float(getattr(logs[0], "opp_pace", 100) or 100)
    line_vs_avg = float(line) - avg5
    return {
        "avg_5g": avg5, "avg_10g": avg10, "avg_season": avg_all,
        "std_5g": std5, "std_10g": std10, "min_5g": min5, "max_5g": max5,
        "avg_home": avg_home, "avg_away": avg_away,
        "minutes_avg_5g": minutes_avg, "games_over_line_5g": over5,
        "games_over_line_10g": over10, "days_rest": rest, "is_b2b": b2b,
        "usage_rate": usage, "opp_def_rank": opp_rank, "home_away": home,
        "team_pace": t_pace, "opp_pace": o_pace, "line_vs_avg5": line_vs_avg
    }

async def build_training_data(stat_col, db):
    from sqlalchemy import select, and_
    from models.orm import GameLog, PropLine
    result = await db.execute(
        select(PropLine).where(
            PropLine.stat_type == stat_col,
            PropLine.actual_value != None
        ).order_by(PropLine.game_date.asc())
    )
    prop_rows = result.scalars().all()
    if len(prop_rows) < 3:
        log.warning(f"[trainer] Not enough labeled props for {stat_col}: {len(prop_rows)}")
        return None, None, None, None
    X_rows, y_clf, y_reg, dates = [], [], [], []
    for prop in prop_rows:
        logs_result = await db.execute(
            select(GameLog).where(
                and_(
                    GameLog.player_id == prop.player_id,
                    GameLog.game_date < prop.game_date
                )
            ).order_by(GameLog.game_date.desc()).limit(15)
        )
        logs = logs_result.scalars().all()
        if len(logs) < 3:
            continue
        feat = build_feature_vector(logs, stat_col, prop.line)
        if feat is None:
            continue
        row = [feat.get(c, 0.0) for c in FEATURE_COLUMNS]
        X_rows.append(row)
        y_clf.append(1 if float(prop.actual_value) > float(prop.line) else 0)
        y_reg.append(float(prop.actual_value))
        dates.append(prop.game_date)
    if len(X_rows) < 3:
        return None, None, None, None
    X = np.array(X_rows, dtype=np.float32)
    return X, np.array(y_clf), np.array(y_reg), dates

def time_split(X, yc, yr, pct=0.8):
    n = len(X)
    s = max(1, int(n * pct))
    if s >= n:
        s = n - 1
    X_tr, y_tr_c, y_tr_r = X[:s].copy(), yc[:s].copy(), yr[:s].copy()
    X_val, y_val_c, y_val_r = X[s:].copy(), yc[s:].copy(), yr[s:].copy()
    # If training set is single-class but the full set has both classes,
    # move the first minority-class sample from val into training.
    if len(np.unique(y_tr_c)) < 2 and len(np.unique(yc)) > 1 and len(X_val) >= 1:
        missing = 1 - int(y_tr_c[0])
        for i, lbl in enumerate(y_val_c):
            if int(lbl) == missing:
                X_tr    = np.vstack([X_tr, X_val[i:i+1]])
                y_tr_c  = np.append(y_tr_c, y_val_c[i])
                y_tr_r  = np.append(y_tr_r, y_val_r[i])
                X_val   = np.delete(X_val, i, axis=0)
                y_val_c = np.delete(y_val_c, i)
                y_val_r = np.delete(y_val_r, i)
                break
    return X_tr, y_tr_c, y_tr_r, X_val, y_val_c, y_val_r

async def train_stat(stat_col, db, model_dir="./artifacts/models", version="v4"):
    log.info(f"[trainer] Training {stat_col}...")
    X, yc, yr, dates = await build_training_data(stat_col, db)
    if X is None or len(X) < 4:
        log.warning(f"[trainer] Skipping {stat_col} — insufficient data ({len(X) if X is not None else 0} samples)")
        return None
    X_tr, y_tr_c, y_tr_r, X_val, y_val_c, y_val_r = time_split(X, yc, yr)
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_val_s = scaler.transform(X_val) if len(X_val) > 0 else X_val
    xgb_clf = XGBClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.1,
        subsample=0.8, use_label_encoder=False, eval_metric="logloss",
        verbosity=0, random_state=42
    )
    xgb_clf.fit(X_tr_s, y_tr_c)
    lgbm_clf = LGBMClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.1,
        subsample=0.8, verbose=-1, random_state=42
    )
    lgbm_clf.fit(X_tr_s, y_tr_c)
    xgb_reg = XGBRegressor(
        n_estimators=100, max_depth=3, learning_rate=0.1,
        subsample=0.8, verbosity=0, random_state=42
    )
    xgb_reg.fit(X_tr_s, y_tr_r)
    if len(X_val_s) >= 2 and len(np.unique(y_val_c)) > 1:
        try:
            xgb_cal = CalibratedClassifierCV(xgb_clf, method="isotonic", cv="prefit")
            xgb_cal.fit(X_val_s, y_val_c)
            lgbm_cal = CalibratedClassifierCV(lgbm_clf, method="isotonic", cv="prefit")
            lgbm_cal.fit(X_val_s, y_val_c)
        except Exception as e:
            log.warning(f"[trainer] Calibration failed for {stat_col}: {e}, using uncalibrated")
            xgb_cal = xgb_clf
            lgbm_cal = lgbm_clf
    else:
        xgb_cal = xgb_clf
        lgbm_cal = lgbm_clf
    if len(X_val_s) > 0 and len(y_val_c) > 0:
        p_xgb = xgb_cal.predict_proba(X_val_s)[:, 1]
        p_lgbm = lgbm_cal.predict_proba(X_val_s)[:, 1]
        p_ens = 0.6 * p_xgb + 0.4 * p_lgbm
        acc = float(accuracy_score(y_val_c, (p_ens > 0.5).astype(int)))
        brier = float(brier_score_loss(y_val_c, p_ens)) if len(np.unique(y_val_c)) > 1 else 0.0
        log.info(f"[trainer] {stat_col}: train={len(X_tr)} val={len(X_val)} acc={acc:.3f} brier={brier:.4f}")
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    for obj, name in [
        (xgb_cal, f"{stat_col}_xgb_{version}.pkl"),
        (lgbm_cal, f"{stat_col}_lgbm_{version}.pkl"),
        (xgb_reg, f"{stat_col}_reg_{version}.pkl"),
        (scaler, f"{stat_col}_scaler_{version}.pkl"),
    ]:
        with open(f"{model_dir}/{name}", "wb") as f:
            pickle.dump(obj, f)
        log.info(f"[trainer] Saved {model_dir}/{name}")
    return {"stat": stat_col, "n_train": len(X_tr), "n_val": len(X_val)}

async def train_all_stats(db, model_dir="./artifacts/models", version="v4"):
    stat_types = ["points", "assists", "rebounds", "three_pm"]
    results = {}
    for stat in stat_types:
        try:
            r = await train_stat(stat, db, model_dir, version)
            if r:
                results[stat] = r
        except Exception as e:
            log.error(f"[trainer] Error training {stat}: {e}", exc_info=True)
    return results
