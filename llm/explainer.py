"""
LLM explainer — generates human-readable prediction explanations via Claude.
Runs async/non-blocking (FIX 9). Returns {"signals": [...], "summary": "..."}.
"""
import asyncio, logging
from core.config import get_settings

cfg = get_settings()
log = logging.getLogger("statrush.llm")


def _fallback_explanation(player_name: str, stat_type: str, prediction: str,
                           probability: float, edge_pct: float) -> dict:
    conf = (
        "high" if edge_pct >= cfg.HIGH_VALUE_EDGE
        else "moderate" if edge_pct >= cfg.MIN_EDGE_PCT
        else "low"
    )
    summary = (
        f"{player_name} projected to go {prediction} on {stat_type} "
        f"({round(probability * 100)}% probability, {conf} confidence, {edge_pct}% edge)."
    )
    signals = [
        f"Model confidence: {round(probability * 100)}%",
        f"Edge: {edge_pct}% ({conf})",
    ]
    return {"signals": signals, "summary": summary}


async def explain_prediction(
    player_name: str,
    stat_type: str,
    line: float,
    prediction: str,
    probability: float,
    edge_pct: float,
    recent_stats: list,
) -> dict:
    if not cfg.ANTHROPIC_API_KEY:
        return _fallback_explanation(player_name, stat_type, prediction, probability, edge_pct)

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=cfg.ANTHROPIC_API_KEY)

        recent_str = ", ".join(str(round(v, 1)) for v in recent_stats[:5]) if recent_stats else "N/A"
        prompt = (
            f"NBA prop bet analysis:\n"
            f"Player: {player_name}\n"
            f"Stat: {stat_type} (line: {line})\n"
            f"Prediction: {prediction} ({round(probability*100)}% probability, {edge_pct}% edge)\n"
            f"Recent feature values: {recent_str}\n\n"
            f"Return a JSON object with two fields:\n"
            f'  "signals": array of 2-3 short bullet strings explaining the key factors\n'
            f'  "summary": one sentence summarizing the prediction\n'
            f"Respond with only valid JSON, no markdown."
        )

        response = await asyncio.wait_for(
            client.messages.create(
                model=cfg.LLM_MODEL,
                max_tokens=cfg.LLM_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=cfg.LLM_TIMEOUT_SEC,
        )
        import json
        return json.loads(response.content[0].text)

    except Exception as e:
        log.warning(f"LLM explain failed: {e}")
        return _fallback_explanation(player_name, stat_type, prediction, probability, edge_pct)
