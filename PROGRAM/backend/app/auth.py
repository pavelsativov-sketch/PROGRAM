"""JWT auth + password hashing + current_shop dependency + token revocation."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .database import get_db

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(raw: str) -> str:
    return pwd_ctx.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return pwd_ctx.verify(raw, hashed)
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(shop_id: int) -> tuple[str, str, datetime]:
    """Возвращает (token, jti, expires_at)."""
    now = _now()
    exp = now + timedelta(minutes=settings.jwt_access_minutes)
    jti = secrets.token_hex(16)
    payload = {
        "sub": str(shop_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "typ": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti, exp


# Обратная совместимость с прежним API
def create_token(shop_id: int) -> str:
    return create_access_token(shop_id)[0]


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except Exception:
        return None


# Имя cookie с access-токеном (httpOnly, SameSite=Lax).
ACCESS_COOKIE = "access_token"


def _extract_token(request: Request, oauth_token: str | None) -> str | None:
    if oauth_token:
        return oauth_token
    # httpOnly cookie — основной канал для браузерного клиента.
    return request.cookies.get(ACCESS_COOKIE)


def current_shop(
    request: Request,
    token: str | None = Depends(oauth2),
    db: Session = Depends(get_db),
) -> models.Shop:
    raw = _extract_token(request, token)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing auth token")
    data = decode_token(raw)
    if not data or "sub" not in data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    jti = data.get("jti")
    if jti and db.get(models.RevokedToken, jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
    try:
        sid = int(data["sub"])
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token subject")
    shop = db.get(models.Shop, sid)
    if not shop or not shop.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Shop not found")
    # Глобальная ротация: токены, выпущенные до tokens_valid_after, считаются недействительными.
    iat = data.get("iat")
    tva = getattr(shop, "tokens_valid_after", None)
    if iat and tva is not None:
        try:
            if hasattr(tva, "timestamp"):
                # SQLite возвращает naive datetime — считаем его UTC.
                if tva.tzinfo is None:
                    tva = tva.replace(tzinfo=UTC)
                tva_ts = int(tva.timestamp())
            else:
                tva_ts = int(tva)
            # Допуск ±2 сек — на расхождение часов между worker'ами и БД-таймстампами.
            if int(iat) + 2 < tva_ts:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token rotated")
        except HTTPException:
            raise
        except Exception:
            pass
    # прокидываем jti вниз, чтобы logout мог отозвать
    request.state.jti = jti
    request.state.token_exp = data.get("exp")
    return shop


def revoke_token(db: Session, jti: str, shop_id: int, exp_ts: int | None = None) -> None:
    if not jti:
        return
    if db.get(models.RevokedToken, jti):
        return
    exp_dt = datetime.fromtimestamp(exp_ts, tz=UTC) if exp_ts else None
    db.add(models.RevokedToken(jti=jti, shop_id=shop_id, expires_at=exp_dt))
    db.commit()


def rotate_tokens_for_shop(db: Session, shop: models.Shop) -> None:
    """Инвалидирует ВСЕ ранее выпущенные JWT этого магазина, сдвигая tokens_valid_after на now.
    Вызывается при login и при смене пароля/email. Новые токены, выданные сразу после,
    имеют iat >= tokens_valid_after и валидны."""
    shop.tokens_valid_after = _now()
    db.flush()
