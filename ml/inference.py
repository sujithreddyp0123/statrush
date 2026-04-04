import numpy as np
import logging
from ml.registry import get
from ml.trainer import FEATURE_COLUMNS, build_feature_vector

log = logging.getLogger("statrush.inference")

def run_inference(logs, stat_type, line, over_juice=-110, version="v4"):
    stat_col = stat_type.value if hasattr(stat_type, 'value') else stat_type
    feat_map = build_feature_vector(logs, stat_col, line)
    if feat_map is None:
        log.warning(f"[inference] No features for {stat_col} — using heuristic")
        return _build_result(_heuristic_prob({}, line), line, line, over_juice, {})
    X_raw = np.array([[feat_map.get(c, 0.0) for c in FEATURE_COLUMNS]], dtype=np.float32)
    scaler = get(stat_col, "scaler", version)
    if scaler is not None:
        try:
            X = scaler.transform(X_raw)
        except Exception as e:
            log.warning(f"[inference] Scaler failed: {e}")
            X = X_raw
    else:
        X = X_raw
    xgb = get(stat_col, "xgb", version)
    lgbm = get(stat_col, "lgbm", version)
    reg = get(stat_col, "reg", version)
    if xgb is not None and lgbm is not None:
        log.info(f"[inference] Using trained model for {stat_col}")
        try:
            p_xgb = float(xgb.predict_proba(X)[0][1])
            p_lgbm = float(lgbm.predict_proba(X)[0][1])
            prob_over = 0.6 * p_xgb + 0.4 * p_lgbm
        except Exception as e:
            log.error(f"[inference] Model predict failed: {e} — falling back")
            prob_over = _heuristic_prob(feat_map, line)
    elif xgb is not None:
        log.info(f"[inference] Using XGB only for {stat_col}")
        try:
            prob_over = float(xgb.predict_proba(X)[0][1])
        except Exception as e:
            log.error(f"[inference] XGB predict failed: {e} — falling back")
            prob_over = _heuristic_prob(feat_map, line)
    else:
        log.warning(f"[inference] No trained model for {stat_col} — using heuristic fallback")
        prob_over = _heuristic_prob(feat_map, line)
    regression = feat_map.get("avg_5g", line)
    if reg is not None:
        try:
            regression = float(reg.predict(X)[0])
        except Exception as e:
            log.warning(f"[inference] Regressor failed: {e}")
    return _build_result(prob_over, regression, line, over_juice, feat_map)

def _heuristic_prob(feat_map, line):
    avg5 = feat_map.get("avg_5g", line)
    hit_rate = feat_map.get("games_over_line_5g", 0.5)
    raw = 0.5 + (avg5 - line) / max(abs(avg5) + 0.001, 1) * 0.3
    return float(min(0.85, max(0.15, 0.6 * raw + 0.4 * hit_rate)))

def _build_result(prob_over, regression, line, over_juice, feat_map):
    prediction = "over" if prob_over > 0.5 else "under"
    final_prob = prob_over if prediction == "over" else (1 - prob_over)
    confidence = int(max(50, min(95, 50 + abs(prob_over - 0.5) * 90)))
    implied = abs(over_juice) / (abs(over_juice) + 100) if over_juice < 0 else 100 / (over_juice + 100)
    edge_pct = round((prob_over - implied) * 100, 2)
    is_high_value = edge_pct >= 8.0
    odds = 1 + (100 / abs(over_juice)) if over_juice < 0 else 1 + (over_juice / 100)
    kelly = round(max(0.0, (edge_pct / 100) / max(odds - 1, 0.01)) * 0.25, 4)
    stat_edge = round(float(regression) - float(line), 2)
    edge_label = "high-value" if is_high_value else ("value" if edge_pct > 3 else "low-value")
    return {
        "prediction": prediction,
        "probability": round(final_prob, 4),
        "confidence": confidence,
        "regression": round(float(regression), 2),
        "implied_prob": round(implied, 4),
        "edge_pct": edge_pct,
        "edge_label": edge_label,
        "stat_edge": stat_edge,
        "is_high_value": is_high_value,
        "kelly_fraction": kelly,
        "feature_snapshot": feat_map,
    }
