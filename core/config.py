from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Literal

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV:            Literal["dev", "staging", "prod"] = "dev"
    LOG_LEVEL:      str   = "INFO"
    LOG_FORMAT:     str   = "json"          # "json" | "text"

    # Database
    DATABASE_URL:       str  = "postgresql+asyncpg://sr:pass@localhost:5432/statrush"
    DB_POOL_SIZE:       int  = 20
    DB_MAX_OVERFLOW:    int  = 10
    DB_POOL_TIMEOUT:    int  = 30

    # Redis
    REDIS_URL:          str  = "redis://localhost:6379/0"
    CACHE_TTL_PRED:     int  = 300
    CACHE_TTL_PLAYERS:  int  = 3600
    CACHE_TTL_FEATURES: int  = 900

    # Celery
    CELERY_BROKER_URL:  str  = "redis://localhost:6379/1"
    CELERY_RESULT_URL:  str  = "redis://localhost:6379/2"

    # ML
    MODEL_DIR:          str  = "./artifacts/models"
    MODEL_VERSION:      str  = "v4"
    MIN_TRAIN_SAMPLES:  int  = 300
    CALIBRATION_METHOD: str  = "isotonic"
    ENSEMBLE_WEIGHTS:   dict = {"xgb": 0.6, "lgbm": 0.4}

    # Feature flags (included in cache key — FIX 6)
    ENABLE_LINE_MOVEMENT:   bool = True
    ENABLE_FATIGUE:         bool = True
    ENABLE_PERSONALIZATION: bool = True

    # Sports data
    SPORTRADAR_KEY:     str  = ""           # empty = use mock layer
    SPORTRADAR_BASE:    str  = "https://api.sportradar.us/nba/trial/v8/en"
    INGEST_BATCH_SIZE:  int  = 50

    # Live data APIs
    BALLDONTLIE_API_KEY: str = ""
    ODDS_API_KEY:        str = ""

    # Anthropic — explanation only
    ANTHROPIC_API_KEY:  str  = ""
    LLM_MODEL:          str  = "claude-sonnet-4-20250514"
    LLM_MAX_TOKENS:     int  = 600
    LLM_CACHE_TTL:      int  = 1800
    LLM_TIMEOUT_SEC:    float = 8.0         # Hard timeout on LLM calls

    # Security (FIX 8)
    JWT_SECRET:         str  = "change-in-prod-32-char-minimum!!"
    JWT_ALGORITHM:      str  = "HS256"
    JWT_EXPIRE_MINUTES: int  = 60
    API_KEY_HEADER:     str  = "X-StatRush-Key"
    VALID_API_KEYS:     list = []           # Populated from env: SR_API_KEY_1, etc.

    # Edge thresholds
    MIN_EDGE_PCT:       float = 3.0
    HIGH_VALUE_EDGE:    float = 8.0

@lru_cache
def get_settings() -> Settings:
    return Settings()

def feature_flag_hash() -> str:
    """Stable short hash of active feature flags — used in cache keys (FIX 6)."""
    import hashlib
    cfg = get_settings()
    flags = f"{cfg.ENABLE_LINE_MOVEMENT}{cfg.ENABLE_FATIGUE}{cfg.MODEL_VERSION}"
    return hashlib.md5(flags.encode()).hexdigest()[:6]
