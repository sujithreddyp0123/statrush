"""
FIX 8 — API security.
Two modes supported:
  1. Bearer JWT token  — for user-facing frontend (issued at /v1/auth/token)
  2. X-StatRush-Key header — for server-to-server integrations

Protected routes: /v1/predictions, /v1/props
Public routes: /v1/players, /health, /v1/auth/token
"""
import time, jwt, logging
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core.config import get_settings

cfg = get_settings()
log = logging.getLogger("statrush.security")
bearer = HTTPBearer(auto_error=False)


def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub":   str(user_id),
        "email": email,
        "iat":   int(time.time()),
        "exp":   int(time.time()) + cfg.JWT_EXPIRE_MINUTES * 60,
    }
    return jwt.encode(payload, cfg.JWT_SECRET, algorithm=cfg.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, cfg.JWT_SECRET, algorithms=[cfg.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """
    Dependency — accepts either JWT Bearer token OR API key header.
    Raises 401/403 if neither is valid.
    """
    # 1. Try API key header first (server-to-server)
    api_key = request.headers.get(cfg.API_KEY_HEADER)
    if api_key:
        if api_key in cfg.VALID_API_KEYS:
            log.debug("auth: api_key accepted")
            return {"type": "api_key", "sub": "service"}
        raise HTTPException(status_code=403, detail="Invalid API key")

    # 2. Try Bearer JWT
    if creds and creds.credentials:
        payload = decode_token(creds.credentials)
        log.debug(f"auth: jwt accepted for {payload.get('sub')}")
        return payload

    raise HTTPException(status_code=401, detail="Authentication required")


async def optional_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict | None:
    """Returns None instead of raising — for endpoints that work for both auth/anon."""
    try:
        return await require_auth(request, creds)
    except HTTPException:
        return None
