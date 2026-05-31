"""Фоновые проверки здоровья бота и проактивные напоминания.

Все функции — идемпотентные джобы для APScheduler. Они открывают собственную
сессию БД (как остальные scheduler-задачи в ``main.py``) и проходят по активным
магазинам, фильтруя строго по ``shop_id``. Анти-спам обеспечивается через
``notifications.record(dedup_key=..., dedup_window=...)``.

Логика вынесена в ``*_for_shop(db, shop, ...)`` хелперы, чтобы тесты могли
вызывать их напрямую со своей сессией без планировщика.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import business_hours, models, notifications
from .database import SessionLocal

log = logging.getLogger(__name__)

PAID_STATUSES = ("paid", "delivered")
IDLE_HOURS = 4               # тишина в рабочее время дольше — алерт
ABANDONED_HOURS = 24         # диалог без активности дольше — дожим


def _shop_tz(shop: models.Shop) -> ZoneInfo:
    try:
        return ZoneInfo(shop.timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _last_incoming_at(db: Session, shop_id: int) -> datetime | None:
    """Время последнего входящего сообщения клиента по магазину."""
    dt = (
        db.query(func.max(models.Message.created_at))
        .join(models.Conversation, models.Message.conversation_id == models.Conversation.id)
        .filter(models.Conversation.shop_id == shop_id, models.Message.role == "user")
        .scalar()
    )
    return _aware(dt)


# ---------------------------------------------------------------------------
# 1) Здоровье бота: канал отвалился / тишина
# ---------------------------------------------------------------------------

def check_bot_health_for_shop(db: Session, shop: models.Shop) -> None:
    # a) WhatsApp-канал был подключён, но мост говорит «не готов» — бот офлайн.
    if shop.wa_connected:
        try:
            from .channels.whatsapp import whatsapp
            st = (whatsapp.status(shop.id) or {}).get("status")
        except Exception:
            st = None
        if st is not None and st not in ("ready", "qr", "starting", "authenticated"):
            shop.wa_connected = False
            notifications.notify_bot_down(db, shop, channel="whatsapp")
            return  # офлайн важнее «тишины»

    # b) Тишина: канал подключён, магазин открыт, но давно нет входящих.
    if shop.wa_connected and getattr(shop, "bot_enabled", True) and business_hours.is_open_now(shop):
        last = _last_incoming_at(db, shop.id)
        if last is not None and (datetime.now(UTC) - last) >= timedelta(hours=IDLE_HOURS):
            notifications.notify_bot_idle(db, shop, hours=IDLE_HOURS)


def check_bot_health() -> None:
    db = SessionLocal()
    try:
        shops = db.query(models.Shop).filter(models.Shop.is_active == True).all()  # noqa: E712
        for shop in shops:
            try:
                check_bot_health_for_shop(db, shop)
            except Exception:
                log.exception("check_bot_health failed shop=%s", shop.id)
        db.commit()
    except Exception:
        log.exception("check_bot_health job failed")
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2) Ежедневная сводка в Telegram
# ---------------------------------------------------------------------------

def build_daily_summary(db: Session, shop: models.Shop, day_local: datetime) -> dict:
    tz = _shop_tz(shop)
    start = day_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    orders = db.query(models.Order).filter_by(shop_id=shop.id).all()
    dialogs = invoices = paid = 0
    revenue = 0.0
    for o in orders:
        created = _aware(o.created_at)
        if not created:
            continue
        local = created.astimezone(tz)
        if not (start <= local < end):
            continue
        invoices += 1
        if o.status in PAID_STATUSES:
            paid += 1
            revenue += float(o.total or 0)

    convs = db.query(models.Conversation).filter_by(shop_id=shop.id).all()
    for c in convs:
        created = _aware(c.created_at)
        if created and start <= created.astimezone(tz) < end:
            dialogs += 1

    return {"dialogs": dialogs, "invoices": invoices, "paid": paid, "revenue": revenue}


def send_daily_summary_for_shop(db: Session, shop: models.Shop, *, force: bool = False) -> bool:
    """Шлёт сводку, если сейчас «час сводки» в таймзоне магазина (или force)."""
    if not (shop.tg_bot_token and shop.tg_chat_id):
        return False
    tz = _shop_tz(shop)
    now_local = datetime.now(tz)
    hour = int(getattr(shop, "daily_summary_hour", 21) or 21)
    if not force and now_local.hour != hour:
        return False
    s = build_daily_summary(db, shop, now_local)
    body = (
        f"Диалогов: {s['dialogs']}\n"
        f"Счетов: {s['invoices']}\n"
        f"Оплат: {s['paid']}\n"
        f"Выручка: {s['revenue']:.0f} {shop.currency or 'RUB'}"
    )
    n = notifications.record(
        db, shop,
        type="daily_summary",
        severity="info",
        title=f"📊 Сводка за {now_local:%d.%m}",
        body=body,
        link="/analytics",
        meta=s,
        dedup_key=f"daily_summary:{now_local:%Y-%m-%d}",
        dedup_window=timedelta(hours=23),
    )
    return n is not None


def send_daily_summaries() -> None:
    db = SessionLocal()
    try:
        shops = db.query(models.Shop).filter(models.Shop.is_active == True).all()  # noqa: E712
        for shop in shops:
            try:
                send_daily_summary_for_shop(db, shop)
            except Exception:
                log.exception("daily summary failed shop=%s", shop.id)
        db.commit()
    except Exception:
        log.exception("send_daily_summaries job failed")
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3) Напоминания о важных датах клиентов
# ---------------------------------------------------------------------------

def _date_matches(date_str: str, recurring: bool, today, tomorrow) -> str | None:
    """Возвращает «сегодня»/«завтра», если дата совпала, иначе None."""
    try:
        y, m, d = (int(x) for x in str(date_str).split("-"))
    except Exception:
        return None
    for label, ref in (("сегодня", today), ("завтра", tomorrow)):
        if recurring:
            if (m, d) == (ref.month, ref.day):
                return label
        else:
            if (y, m, d) == (ref.year, ref.month, ref.day):
                return label
    return None


def check_reminders_for_shop(db: Session, shop: models.Shop) -> int:
    tz = _shop_tz(shop)
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)
    sent = 0
    customers = (
        db.query(models.Customer)
        .filter(models.Customer.shop_id == shop.id)
        .filter(models.Customer.important_dates.isnot(None))
        .all()
    )
    for c in customers:
        for item in (c.important_dates or []):
            if not isinstance(item, dict):
                continue
            when = _date_matches(item.get("date", ""), bool(item.get("recurring")), today, tomorrow)
            if when:
                label = (item.get("label") or "Важная дата").strip()
                if notifications.notify_reminder(db, shop, c, label, when) is not None:
                    sent += 1
    return sent


def check_reminders() -> None:
    db = SessionLocal()
    try:
        shops = db.query(models.Shop).filter(models.Shop.is_active == True).all()  # noqa: E712
        for shop in shops:
            try:
                check_reminders_for_shop(db, shop)
            except Exception:
                log.exception("reminders failed shop=%s", shop.id)
        db.commit()
    except Exception:
        log.exception("check_reminders job failed")
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4) Дожим брошенных диалогов
# ---------------------------------------------------------------------------

FOLLOWUP_TEXT = (
    "Здравствуйте! Я на связи 🌸 Если ещё актуально — помогу подобрать букет "
    "и оформить заказ. Подскажите, что вам приглянулось?"
)


def followup_abandoned_for_shop(db: Session, shop: models.Shop) -> int:
    """Находит активные диалоги без активности > ABANDONED_HOURS и дожимает их."""
    if not getattr(shop, "followup_enabled", True):
        return 0
    cutoff = datetime.now(UTC) - timedelta(hours=ABANDONED_HOURS)
    convs = (
        db.query(models.Conversation)
        .filter(models.Conversation.shop_id == shop.id, models.Conversation.status == "active")
        .all()
    )
    nudged = 0
    for conv in convs:
        msgs = conv.messages or []
        if not msgs:
            continue
        last_at = _aware(max((m.created_at for m in msgs if m.created_at), default=None))
        if last_at is None or last_at > cutoff:
            continue
        # Уже дожимали этот диалог? Помечаем флагом в variables, чтобы не слать дважды.
        vars_ = dict(conv.variables or {})
        if vars_.get("_followup_sent"):
            continue
        try:
            msg = models.Message(conversation_id=conv.id, role="bot", text=FOLLOWUP_TEXT, meta={})
            db.add(msg)
            vars_["_followup_sent"] = True
            conv.variables = vars_
            db.flush()
            cust = conv.customer
            ok = False
            if cust and cust.channel:
                from .dispatcher import _deliver
                try:
                    ok = _deliver(shop.id, cust.channel, cust.external_id, FOLLOWUP_TEXT)
                except Exception:
                    log.exception("followup delivery failed conv=%s", conv.id)
            msg.meta = {"sent": bool(ok), "followup": True}
            notifications.notify_followup(db, shop, conv)
            nudged += 1
        except Exception:
            log.exception("followup failed conv=%s", conv.id)
    return nudged


def followup_abandoned_dialogs() -> None:
    db = SessionLocal()
    try:
        shops = db.query(models.Shop).filter(models.Shop.is_active == True).all()  # noqa: E712
        for shop in shops:
            try:
                followup_abandoned_for_shop(db, shop)
            except Exception:
                log.exception("followup failed shop=%s", shop.id)
        db.commit()
    except Exception:
        log.exception("followup_abandoned_dialogs job failed")
        db.rollback()
    finally:
        db.close()
