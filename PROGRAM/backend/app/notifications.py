"""Центр уведомлений магазина.

Единая точка создания уведомлений: пишем строку в таблицу ``notifications``
(её показывает «колокольчик» в UI и читает браузер-пуш через поллинг фида) и,
если у магазина настроен Telegram, дублируем туда же.

Все функции принимают активную сессию ``db`` и фильтруют по ``shop.id`` —
мультитенантность сохраняется. Любая ошибка отправки в Telegram гасится:
запись в БД важнее, чем доставка во внешний канал.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from . import models, notifier

log = logging.getLogger(__name__)

# Эмодзи-префикс для Telegram по серьёзности.
_SEV_ICON = {"info": "🔔", "warning": "⚠️", "critical": "🛑"}


def _recent_exists(db: Session, shop_id: int, dedup_key: str, window: timedelta) -> bool:
    """Есть ли свежее уведомление с тем же dedup_key в окне (анти-спам)."""
    if not dedup_key:
        return False
    since = datetime.now(UTC) - window
    q = (
        db.query(models.Notification.id)
        .filter(models.Notification.shop_id == shop_id)
        .filter(models.Notification.dedup_key == dedup_key)
        .filter(models.Notification.created_at >= since)
    )
    return db.query(q.exists()).scalar() or False


def record(
    db: Session,
    shop: models.Shop,
    *,
    type: str,
    title: str,
    body: str = "",
    severity: str = "info",
    link: str = "",
    meta: Optional[dict] = None,
    dedup_key: str = "",
    dedup_window: Optional[timedelta] = None,
    telegram: bool = True,
) -> Optional[models.Notification]:
    """Создаёт уведомление (с анти-спамом по dedup_key) и дублирует в Telegram.

    Возвращает созданную запись или ``None``, если сработал анти-спам.
    """
    if dedup_window is not None and _recent_exists(db, shop.id, dedup_key, dedup_window):
        return None

    n = models.Notification(
        shop_id=shop.id,
        type=type,
        severity=severity or "info",
        title=title[:255],
        body=body or "",
        link=link or "",
        meta=meta or {},
        dedup_key=dedup_key or "",
    )
    db.add(n)
    db.flush()

    if telegram:
        try:
            icon = _SEV_ICON.get(severity, "🔔")
            text = f"{icon} <b>{notifier._esc(title)}</b>"
            if body:
                text += f"\n{notifier._esc(body)}"
            notifier.send_message(shop, text)
        except Exception:
            log.exception("notifications: telegram fan-out failed shop=%s type=%s", shop.id, type)

    return n


# ---------------------------------------------------------------------------
# Высокоуровневые событийные хелперы
# ---------------------------------------------------------------------------

def notify_handoff(db: Session, shop: models.Shop, conv: models.Conversation, reason: str = "") -> None:
    """«Нужен менеджер»: handoff из сценария/агента/команды клиента."""
    cust = conv.customer
    name = ((cust.name if cust else "") or (cust.external_id if cust else "") or "клиент").strip()
    last_user = next((m.text for m in reversed(conv.messages or []) if m.role == "user"), "")
    snippet = (last_user or reason or "").strip()[:200]
    body = f"Клиент: {name}"
    if snippet:
        body += f"\nСообщение: «{snippet}»"
    record(
        db, shop,
        type="handoff",
        severity="warning",
        title="Нужен менеджер",
        body=body,
        link=f"/conversations?focus={conv.id}",
        meta={"conversation_id": conv.id, "customer": name},
        dedup_key=f"handoff:{conv.id}",
        dedup_window=timedelta(minutes=30),
    )


def notify_bot_down(db: Session, shop: models.Shop, channel: str = "whatsapp") -> None:
    """Канал бота отвалился — клиенты не получают ответы."""
    record(
        db, shop,
        type="bot_down",
        severity="critical",
        title="Бот офлайн — клиенты без ответа",
        body=f"Канал {channel} отключился. Переподключите его в разделе «Каналы», иначе сообщения клиентов остаются без ответа.",
        link="/channels",
        dedup_key=f"bot_down:{channel}",
        dedup_window=timedelta(hours=6),
    )


def notify_bot_disabled(db: Session, shop: models.Shop) -> None:
    """Бот выключен в настройках, но клиент пишет — диалоги уходят менеджеру."""
    record(
        db, shop,
        type="bot_disabled",
        severity="warning",
        title="Бот выключен — отвечает менеджер",
        body="Пришло сообщение клиента, но AI-бот выключен в настройках. Диалог передан менеджеру. Включите бота в «Настройки → AI-бот».",
        link="/settings",
        dedup_key="bot_disabled",
        dedup_window=timedelta(hours=6),
    )


def notify_bot_idle(db: Session, shop: models.Shop, hours: int) -> None:
    """Канал подключён, но давно нет входящих в рабочее время — возможный сбой."""
    record(
        db, shop,
        type="bot_idle",
        severity="warning",
        title="Тишина в диалогах",
        body=f"За последние {hours} ч в рабочее время не было ни одного входящего сообщения. Проверьте, что номер на связи и бот отвечает.",
        link="/channels",
        dedup_key="bot_idle",
        dedup_window=timedelta(hours=12),
    )


def notify_ai_error(db: Session, shop: models.Shop, detail: str = "") -> None:
    """AI-провайдер сыпет ошибками — ответы деградируют."""
    record(
        db, shop,
        type="ai_error",
        severity="warning",
        title="Сбои AI-провайдера",
        body="AI не отвечает стабильно — проверьте ключ и лимиты в «Настройки → AI-бот». Бот временно отвечает в упрощённом режиме."
        + (f"\n{detail}" if detail else ""),
        link="/settings",
        dedup_key="ai_error",
        dedup_window=timedelta(hours=1),
    )


def notify_reminder(db: Session, shop: models.Shop, customer: models.Customer, label: str, when: str) -> Optional[models.Notification]:
    """Напоминание о важной дате клиента — повод предложить букет повторно."""
    name = (customer.name or customer.external_id or "клиент").strip()
    return record(
        db, shop,
        type="reminder",
        severity="info",
        title=f"Скоро повод у клиента: {name}",
        body=f"{label} — {when}. Хороший момент написать и предложить букет.",
        link=f"/customers?focus={customer.id}",
        meta={"customer_id": customer.id, "label": label, "when": when},
        dedup_key=f"reminder:{customer.id}:{label}:{when}",
        dedup_window=timedelta(days=2),
    )


def notify_followup(db: Session, shop: models.Shop, conv: models.Conversation) -> None:
    """Брошенный диалог — бот отправил дожим, фиксируем это в центре уведомлений."""
    cust = conv.customer
    name = ((cust.name if cust else "") or (cust.external_id if cust else "") or "клиент").strip()
    record(
        db, shop,
        type="followup",
        severity="info",
        title="Дожали брошенный диалог",
        body=f"Клиент {name} пропал на полпути — бот отправил мягкое напоминание вернуться к выбору букета.",
        link=f"/conversations?focus={conv.id}",
        meta={"conversation_id": conv.id},
        dedup_key=f"followup:{conv.id}",
        dedup_window=timedelta(days=3),
        telegram=False,
    )
