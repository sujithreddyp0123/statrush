"""
FIX 11 — Structured JSON logging.
All prediction requests, inference runs, LLM calls, and errors
are logged in a machine-parseable format for observability.
"""
import logging, sys, json, time
from core.config import get_settings

cfg = get_settings()


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)
        # Attach any extra fields passed via extra={}
        for key in ("player_id", "stat_type", "model_version", "latency_ms",
                    "edge_pct", "error_code", "user_id"):
            if hasattr(record, key):
                log_obj[key] = getattr(record, key)
        return json.dumps(log_obj)


def setup_logging():
    root = logging.getLogger("statrush")
    root.setLevel(getattr(logging, cfg.LOG_LEVEL.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    if cfg.LOG_FORMAT == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
        ))
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
    return root
