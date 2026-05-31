from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import log_action
from ..auth import (
    ACCESS_COOKIE,
    create_access_token,
    current_shop,
    hash_password,
    revoke_token,
    rotate_tokens_for_shop,
    verify_password,
)
from ..config import settings
from ..database import get_db
from ..rate_limit import limiter
from ..seed import seed_shop_defaults

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_auth_cookie(resp: Response, token: str) -> None:
    """Ставим httpOnly cookie с access-токеном.
    SameSite=Strict + Secure только на prod (на localhost http Secure ломает cookie).
    """
    resp.set_cookie(
        key=ACCESS_COOKIE,
        value=token,
        httponly=True,
        secure=(settings.env == "prod"),
        samesite="strict",
        max_age=settings.jwt_access_minutes * 60,
        path="/",
    )


def _clear_auth_cookie(resp: Response) -> None:
    resp.delete_cookie(ACCESS_COOKIE, path="/")


@router.post("/signup", response_model=schemas.TokenOut)
@limiter.limit(settings.rate_limit_signup)
def signup(
    request: Request,
    payload: schemas.SignupIn,
    response: Response,
    db: Session = Depends(get_db),
):
    if len(payload.password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пароль должен быть не короче 8 символов")
    existing = db.query(models.Shop).filter_by(email=payload.email.lower()).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email уже зарегистрирован")
    try:
        shop = models.Shop(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            name=payload.name or "My Flower Shop",
        )
        db.add(shop)
        db.flush()
        seed_shop_defaults(db, shop)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Не удалось создать магазин")
    log_action(db, "signup", shop_id=shop.id, request=request)
    token, _, _ = create_access_token(shop.id)
    _set_auth_cookie(response, token)
    return schemas.TokenOut(access_token=token)


@router.post("/login", response_model=schemas.TokenOut)
@limiter.limit(settings.rate_limit_login)
def login(
    request: Request,
    payload: schemas.LoginIn,
    response: Response,
    db: Session = Depends(get_db),
):
    shop = db.query(models.Shop).filter_by(email=payload.email.lower()).first()
    if not shop or not verify_password(payload.password, shop.password_hash):
        log_action(db, "login_failed", shop_id=(shop.id if shop else None), request=request,
                   meta={"email": payload.email.lower()})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный email или пароль")
    # Ротация: предыдущие активные токены инвалидируются (защита от украденной cookie).
    rotate_tokens_for_shop(db, shop)
    db.commit()
    log_action(db, "login", shop_id=shop.id, request=request)
    token, _, _ = create_access_token(shop.id)
    _set_auth_cookie(response, token)
    return schemas.TokenOut(access_token=token)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    shop: models.Shop = Depends(current_shop),
    db: Session = Depends(get_db),
):
    jti = getattr(request.state, "jti", None)
    exp = getattr(request.state, "token_exp", None)
    if jti:
        revoke_token(db, jti, shop.id, exp)
    log_action(db, "logout", shop_id=shop.id, request=request)
    _clear_auth_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=schemas.ShopOut)
def me(shop: models.Shop = Depends(current_shop)):
    return shop


@router.put("/me", response_model=schemas.ShopOut)
def update_me(
    request: Request,
    payload: schemas.ShopSettingsIn,
    shop: models.Shop = Depends(current_shop),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    changed = [k for k in data if getattr(shop, k, None) != data[k]]
    for k, v in data.items():
        setattr(shop, k, v)
    db.commit()
    db.refresh(shop)
    if changed:
        # ai_api_key логируем как факт смены, без значения.
        log_action(db, "settings_update", shop_id=shop.id, request=request,
                   meta={"fields": changed, "ai_key_changed": "ai_api_key" in changed})
    return shop
