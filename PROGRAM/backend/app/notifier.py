"""Уведомления магазину: Telegram-бот.

Простой слой поверх Bot API: магазин получает «новый заказ #142, 18 000 ₸,
доставка завтра» прямо в Telegram. Это самый дешёвый и надёжный канал
для нотификаций (цветочные магазины почти всегда сидят в Telegram).

Настройка:
1. Магазин создаёт бота через @BotFather, получает token.
2. Магазин пишет своему боту что-то (любое сообщение).
3. Магазин получает chat_id через `/api/notifications/telegram/test` —
   мы дёргаем `getUpdates` и достаём chat_id из последнего сообщения.
4. Магазин сохраняет token + chat_id в Settings — мы шлём по нему
   уведомления при handoff / paid / new_order.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from . import models

log = logging.getLogger(__name__)

_TG_API = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 8


def _post(token: str, method: str, payload: dict) -> Optional[dict]:
    if not token:
        return None
    url = _TG_API.format(token=token, method=method)
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.post(url, json=payload)
        if r.status_code >= 400:
            log.warning("telegram %s failed: status=%s body=%r", method, r.status_code, r.text[:200])
            return None
        return r.json()
    except Exception as e:
        log.warning("telegram %s exception: %s", method, e)
        return None


def send_message(shop: models.Shop, text: str) -> bool:
    """Отправляет сообщение в Telegram-канал магазина. Возвращает True при успехе.
    Если token/chat_id не заданы — тихо ничего не делает."""
    token = (shop.tg_bot_token or "").strip()
    chat_id = (shop.tg_chat_id or "").strip()
    if not token or not chat_id:
        return False
    r = _post(token, "sendMessage", {
        "chat_id": chat_id,
        "text": text[:4096],  # Telegram limit
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })
    return bool(r and r.get("ok"))


def discover_chat_id(token: str) -> Optional[str]:
    """Дёргает getUpdates у Telegram и возвращает chat_id из последнего апдейта.
    Используется в UI Settings для автоматического получения chat_id."""
    if not token:
        return None
    url = _TG_API.format(token=token, method="getUpdates")
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.get(url, params={"limit": 5, "timeout": 0})
        if r.status_code >= 400:
            return None
        data = r.json()
        if not data.get("ok"):
            return None
        results = data.get("result") or []
        for upd in reversed(results):
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat") or {}
            cid = chat.get("id")
            if cid:
                return str(cid)
    except Exception as e:
        log.warning("discover_chat_id failed: %s", e)
    return None


# ---------- Высокоуровневые событийные хелперы ----------

def notify_handoff(shop: models.Shop, conversation_id: int, customer_name: str, last_text: str) -> None:
    """Сообщение «нужен менеджер»."""
    if not (shop.tg_bot_token and shop.tg_chat_id):
        return
    name = (customer_name or "клиент").strip()
    snippet = (last_text or "").strip()[:200].replace("<", "&lt;").replace(">", "&gt;")
    text = (
        f"🔔 <b>Нужен менеджер</b>\n"
        f"Клиент: <b>{_esc(name)}</b>\n"
        f"Сообщение: «{snippet}»\n"
        f"Диалог #{conversation_id}"
    )
    send_message(shop, text)


def notify_new_order(shop: models.Shop, order: models.Order) -> None:
    """Сообщение про новый счёт (пока бот пендингует оплату)."""
    if not (shop.tg_bot_token and shop.tg_chat_id):
        return
    details = order.details or {}
    items = order.items or []
    items_str = ", ".join(f"{i.get('name','?')}×{i.get('qty',1)}" for i in items) or "—"
    text = (
        f"🌷 <b>Новый счёт #{order.id}</b>\n"
        f"Сумма: <b>{order.total:.0f} {shop.currency}</b>\n"
        f"Клиент: {_esc(details.get('name') or '—')}, {_esc(details.get('phone') or '—')}\n"
        f"Доставка: {_esc(details.get('delivery_date') or '—')}\n"
        f"Адрес: {_esc(details.get('address') or '—')}\n"
        f"Товары: {_esc(items_str)}"
    )
    send_message(shop, text)


def notify_paid(shop: models.Shop, order: models.Order) -> None:
    """Сообщение про подтверждённую оплату — самое важное событие для магазина."""
    if not (shop.tg_bot_token and shop.tg_chat_id):
        return
    details = order.details or {}
    text = (
        f"✅ <b>Заказ #{order.id} оплачен</b>\n"
        f"Сумма: <b>{order.total:.0f} {shop.currency}</b>\n"
        f"Клиент: {_esc(details.get('name') or '—')}, {_esc(details.get('phone') or '—')}\n"
        f"Доставка: {_esc(details.get('delivery_date') or '—')}, {_esc(details.get('address') or '—')}"
    )
    send_message(shop, text)


def _esc(s: str) -> str:
    return str(s or "").replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")[:300]
