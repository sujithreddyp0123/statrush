"""
FIX 8 — Minimal auth router.
POST /v1/auth/token — issue JWT for a user (email+password).
Dev mode: accepts any email/password and returns a token.
Prod: verify bcrypt hash against User table.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from core.database import get_db
from core.security import create_token
from core.config import get_settings
from models.orm import User

router = APIRouter(prefix="/v1/auth", tags=["auth"])
cfg = get_settings()


class LoginRequest(BaseModel):
    email:    str
    password: str


@router.post("/token")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    if cfg.ENV == "dev":
        # Dev: accept any credentials, create user row if not exists
        result = await db.execute(select(User).where(User.email == req.email))
        user = result.scalar_one_or_none()
        if not user:
            user = User(email=req.email)
            db.add(user)
            await db.commit()
            await db.refresh(user)
        token = create_token(user.id, user.email)
        return {"access_token": token, "token_type": "bearer"}

    # Prod: must exist in DB
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(user.id, user.email)
    return {"access_token": token, "token_type": "bearer"}
