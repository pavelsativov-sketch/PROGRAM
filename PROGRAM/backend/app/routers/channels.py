import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..audit import log_action
from ..auth import current_shop
from ..channels.instagram import ig_manager
from ..channels.whatsapp import whatsapp
from ..config import settings
from ..database import get_db
from ..dispatcher import handle_incoming, persist_incoming
from ..rate_limit import limiter

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/channels", tags=["channels"])


# ---------- WhatsApp ----------
@router.get("/whatsapp/status")
def wa_status(shop: models.Shop = Depends(current_shop)):
    return whatsapp.status(shop.id)


@router.post("/whatsapp/connect")
@limiter.limit(settings.rate_limit_wa_connect)
def wa_connect(request: Request, shop: models.Shop = Depends(current_shop), db: Session = Depends(get_db)):
    log_action(db, "wa_connect", shop_id=shop.id, request=request)
    return whatsapp.connect(shop.id)


@router.get("/whatsapp/qr")
def wa_qr(shop: models.Shop = Depends(current_shop)):
    return whatsapp.qr(shop.id)


@router.post("/whatsapp/logout")
def wa_logout(request: Request, shop: models.Shop = Depends(current_shop), db: Session = Depends(get_db)):
    r = whatsapp.logout(shop.id)
    shop.wa_connected = False
    shop.wa_phone = ""
    db.commit()
    log_action(db, "wa_logout", shop_id=shop.id, request=request)
    return r


# Внутренний webhook от Node-моста
@router.post("/whatsapp/webhook")
async def wa_webhook(
    req: Request,
    background: BackgroundTasks,
    x_bridge_secret: str | None = Header(default=None),
    x_bridge_signature: str | None = Header(default=None),
    x_bridge_timestamp: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    # Защита от replay: timestamp ± wa_webhook_max_skew секунд. Подпись = HMAC(secret, ts + "." + body).
    raw = await req.body()
    sig_ok = False
    if x_bridge_signature and x_bridge_timestamp:
        try:
            skew = abs(int(time.time()) - int(x_bridge_timestamp))
        except ValueError:
            skew = settings.wa_webhook_max_skew + 1
        if skew <= settings.wa_webhook_max_skew:
            mac_input = x_bridge_timestamp.encode("ascii") + b"." + raw
            expected = hmac.new(
                settings.wa_bridge_secret.encode("utf-8"), mac_input, hashlib.sha256
            ).hexdigest()
            sig_ok = hmac.compare_digest(expected, x_bridge_signature)
        else:
            log.warning("wa webhook timestamp skew too large: %s", skew)
    # Backward compat: legacy подпись без timestamp (по чистому body) — принимаем только не в prod.
    legacy_sig_ok = False
    if not sig_ok and x_bridge_signature and settings.env != "prod":
        legacy_expected = hmac.new(
            settings.wa_bridge_secret.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
        legacy_sig_ok = hmac.compare_digest(legacy_expected, x_bridge_signature)
    # Совсем legacy: только X-Bridge-Secret в plain (не prod).
    secret_ok = (
        settings.env != "prod"
        and bool(x_bridge_secret)
        and hmac.compare_digest(x_bridge_secret, settings.wa_bridge_secret)
    )
    if not (sig_ok or legacy_sig_ok or secret_ok):
        log.warning("wa webhook auth failed: sig_ok=%s legacy=%s secret_ok=%s ts=%s",
                    sig_ok, legacy_sig_ok, secret_ok, x_bridge_timestamp)
        raise HTTPException(401, "bad secret")
    try:
        import json
        body = json.loads(raw or b"{}")
    except Exception:
        raise HTTPException(400, "bad json")
    log.info("wa webhook event=%s shop=%s from=%s text_len=%s",
             body.get("event"), body.get("shop_id"),
             body.get("from"), len(body.get("text") or ""))
    shop_id = int(body.get("shop_id") or 0)
    event = body.get("event", "message")
    if event == "ready":
        shop = db.get(models.Shop, shop_id)
        if shop:
            shop.wa_connected = True
            shop.wa_phone = body.get("me") or ""
            db.commit()
        return {"ok": True}
    if event == "disconnected":
        shop = db.get(models.Shop, shop_id)
        if shop:
            shop.wa_connected = False
            db.commit()
        return {"ok": True}
    frm = body.get("from")
    text = body.get("text")
    name = body.get("name") or ""
    if not frm or not text or not shop_id:
        return {"ok": False}
    # ВАЖНО: сохраняем входящее сообщение СИНХРОННО в inbox до постановки задачи.
    # Если backend упадёт между ACK и AI-обработкой — scheduler ретраит pending-записи.
    inbox_id = persist_incoming(shop_id, "whatsapp", str(frm), str(text), str(name))
    background.add_task(
        handle_incoming, shop_id, "whatsapp", str(frm), str(text), str(name), inbox_id
    )
    return {"ok": True}


# ---------- Instagram ----------
# Internal note: Meta агрессивно блокирует instagrapi-логины с серверных IP.
# Для боевой работы магазину нужен residential/mobile прокси (поле Shop.ig_proxy).
# Канал намеренно «best-effort» — UI показывает понятный hint при ошибке.


class IGLoginIn(BaseModel):
    username: str
    password: str
    code: str = ""
    proxy: str = ""


@router.get("/instagram/status")
def ig_status(shop: models.Shop = Depends(current_shop)):
    info = ig_manager.get(shop.id).info()
    # Возвращаем сохранённый username из БД, если сессия ещё не загружена в память.
    if not info.get("username") and shop.ig_username:
        info["username"] = shop.ig_username
    info["connected_db"] = bool(shop.ig_connected)
    return info


@router.post("/instagram/login")
@limiter.limit(settings.rate_limit_wa_connect)
def ig_login(
    request: Request,
    payload: IGLoginIn,
    shop: models.Shop = Depends(current_shop),
    db: Session = Depends(get_db),
):
    sess = ig_manager.get(shop.id)
    proxy = (payload.proxy or shop.ig_proxy or "").strip()
    r = sess.login(payload.username.strip(), payload.password, payload.code.strip(), proxy)
    if r.get("ok"):
        shop.ig_username = payload.username.strip()
        shop.ig_connected = True
        if proxy and proxy != shop.ig_proxy:
            shop.ig_proxy = proxy
        db.commit()
        log_action(db, "ig_login", shop_id=shop.id, request=request,
                   meta={"username_set": True, "proxy_changed": bool(proxy)})
    else:
        log_action(db, "ig_login_failed", shop_id=shop.id, request=request,
                   meta={"hint": r.get("hint", "")})
    return r


@router.post("/instagram/logout")
def ig_logout(
    request: Request,
    shop: models.Shop = Depends(current_shop),
    db: Session = Depends(get_db),
):
    ig_manager.get(shop.id).logout()
    shop.ig_connected = False
    shop.ig_username = ""
    db.commit()
    log_action(db, "ig_logout", shop_id=shop.id, request=request)
    return {"ok": True}


class IGProxyIn(BaseModel):
    proxy: str = ""


@router.post("/instagram/proxy")
def ig_set_proxy(
    request: Request,
    payload: IGProxyIn,
    shop: models.Shop = Depends(current_shop),
    db: Session = Depends(get_db),
):
    """Сохраняет прокси-строку для IG в БД (зашифровано). Применится при следующем логине."""
    shop.ig_proxy = (payload.proxy or "").strip()
    db.commit()
    log_action(db, "ig_proxy_set", shop_id=shop.id, request=request,
               meta={"proxy_changed": True})
    return {"ok": True}
