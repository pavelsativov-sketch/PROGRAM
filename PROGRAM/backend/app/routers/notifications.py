"""Роутер уведомлений: центр уведомлений (фид) + настройки Telegram."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, notifier
from ..auth import current_shop
from ..database import get_db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _serialize(n: models.Notification) -> dict:
    created = n.created_at
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return {
        "id": n.id,
        "type": n.type,
        "severity": n.severity or "info",
        "title": n.title,
        "body": n.body or "",
        "link": n.link or "",
        "meta": n.meta or {},
        "is_read": n.read_at is not None,
        "created_at": created.isoformat() if created else None,
    }


@router.get("")
def list_notifications(
    unread: bool = False,
    limit: int = 30,
    offset: int = 0,
    shop: models.Shop = Depends(current_shop),
    db: Session = Depends(get_db),
):
    """Лента уведомлений магазина (новые сверху) + счётчик непрочитанных."""
    limit = max(1, min(limit, 100))
    q = db.query(models.Notification).filter(models.Notification.shop_id == shop.id)
    if unread:
        q = q.filter(models.Notification.read_at.is_(None))
    items = (
        q.order_by(models.Notification.created_at.desc(), models.Notification.id.desc())
        .offset(max(0, offset))
        .limit(limit)
        .all()
    )
    unread_count = (
        db.query(models.Notification)
        .filter(models.Notification.shop_id == shop.id, models.Notification.read_at.is_(None))
        .count()
    )
    return {"items": [_serialize(n) for n in items], "unread_count": unread_count}


@router.get("/unread-count")
def unread_count(shop: models.Shop = Depends(current_shop), db: Session = Depends(get_db)):
    count = (
        db.query(models.Notification)
        .filter(models.Notification.shop_id == shop.id, models.Notification.read_at.is_(None))
        .count()
    )
    return {"count": count}


@router.post("/{nid}/read")
def mark_read(nid: int, shop: models.Shop = Depends(current_shop), db: Session = Depends(get_db)):
    n = (
        db.query(models.Notification)
        .filter(models.Notification.id == nid, models.Notification.shop_id == shop.id)
        .first()
    )
    if not n:
        raise HTTPException(404, "Уведомление не найдено")
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
        db.commit()
    return {"ok": True}


@router.post("/read-all")
def mark_all_read(shop: models.Shop = Depends(current_shop), db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    updated = (
        db.query(models.Notification)
        .filter(models.Notification.shop_id == shop.id, models.Notification.read_at.is_(None))
        .update({models.Notification.read_at: now}, synchronize_session=False)
    )
    db.commit()
    return {"ok": True, "updated": int(updated or 0)}


@router.delete("/{nid}")
def delete_notification(nid: int, shop: models.Shop = Depends(current_shop), db: Session = Depends(get_db)):
    n = (
        db.query(models.Notification)
        .filter(models.Notification.id == nid, models.Notification.shop_id == shop.id)
        .first()
    )
    if not n:
        raise HTTPException(404, "Уведомление не найдено")
    db.delete(n)
    db.commit()
    return {"ok": True}


class TgTestIn(BaseModel):
    # Опционально: если магазин ещё не сохранил, можно протестить с ad-hoc токеном
    token: str | None = None
    chat_id: str | None = None


@router.post("/telegram/test")
def telegram_test(
    payload: TgTestIn,
    shop: models.Shop = Depends(current_shop),
    db: Session = Depends(get_db),
):
    """Отправляет тестовое сообщение в Telegram-канал магазина.
    Без сохранения настроек — нужно для проверки перед сохранением."""
    token = (payload.token or shop.tg_bot_token or "").strip()
    chat_id = (payload.chat_id or shop.tg_chat_id or "").strip()
    if not token or not chat_id:
        raise HTTPException(400, "Заполните Telegram bot token и chat_id")
    # Лёгкий хак: подсовываем «магазин-наследник» с переданными значениями.
    fake_shop = type("S", (), {
        "tg_bot_token": token,
        "tg_chat_id": chat_id,
    })()
    ok = notifier.send_message(fake_shop, "✅ Тестовое сообщение от Floral · уведомления настроены.")
    return {"ok": bool(ok)}


@router.post("/telegram/discover-chat")
def telegram_discover_chat(
    payload: TgTestIn,
    shop: models.Shop = Depends(current_shop),
):
    """Достаёт chat_id последнего сообщения, которое бот получил.
    Магазин нажимает кнопку «У меня уже есть бот, найди chat_id», предварительно
    написав боту что-то — мы возвращаем chat_id."""
    token = (payload.token or shop.tg_bot_token or "").strip()
    if not token:
        raise HTTPException(400, "Сначала укажите bot token")
    chat_id = notifier.discover_chat_id(token)
    if not chat_id:
        raise HTTPException(
            404,
            "Не удалось найти ваш chat_id. Откройте чат с ботом и напишите ему любое сообщение, потом нажмите ещё раз.",
        )
    return {"chat_id": chat_id}
