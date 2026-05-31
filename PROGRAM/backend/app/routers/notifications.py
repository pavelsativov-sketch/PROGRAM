"""Роутер настроек уведомлений: тест отправки, авто-discover chat_id."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, notifier
from ..auth import current_shop
from ..database import get_db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


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
