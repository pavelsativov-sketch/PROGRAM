"""Аналитика для дашборда «Сегодня».

Возвращает агрегаты, которые рисует фронт: KPI за сегодня/неделю/месяц,
почасовое распределение, разбивка по каналам, топ товаров.
Фильтрация по shop_id обязательна (мультитенантность).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..auth import current_shop
from ..database import get_db

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# Статусы оплаченных заказов (учитываем в выручке).
PAID_STATUSES = ("paid", "delivered")


def _shop_tz(shop: models.Shop) -> ZoneInfo:
    try:
        return ZoneInfo(shop.timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _to_aware_utc(dt: datetime | None) -> datetime | None:
    """SQLite иногда возвращает naive datetime, хотя поле DateTime(timezone=True).
    Приводим к aware UTC, иначе сравнения с tz-aware now() рушатся.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    tz = _shop_tz(shop)
    now_local = datetime.now(tz)
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=6)
    month_start = today_start - timedelta(days=29)

    # Все заказы магазина (с пагинацией не заморачиваемся: для
    # средне-маленького магазина пара сотен в день — норма).
    orders: list[models.Order] = (
        db.query(models.Order).filter_by(shop_id=shop.id).all()
    )

    today_revenue = 0.0
    today_orders = 0
    today_paid_orders = 0
    week_revenue = 0.0
    prev_week_revenue = 0.0   # неделя ДО предыдущих 7 дней — для тренда
    month_revenue = 0.0
    pipeline: dict[str, int] = {}
    hourly = [0] * 24
    by_channel: dict[str, int] = {}
    today_orders_list: list[dict] = []

    prev_week_start = week_start - timedelta(days=7)

    for o in orders:
        created = _to_aware_utc(o.created_at)
        if created is None:
            continue
        local = created.astimezone(tz)
        is_paid = o.status in PAID_STATUSES
        pipeline[o.status] = pipeline.get(o.status, 0) + 1

        if local >= today_start:
            today_orders += 1
            hourly[local.hour] += 1
            if is_paid:
                today_paid_orders += 1
                today_revenue += float(o.total or 0)
            today_orders_list.append({
                "id": o.id,
                "status": o.status,
                "total": float(o.total or 0),
                "items": o.items or [],
                "details": o.details or {},
                "created_at": created.isoformat(),
                "customer_id": o.customer_id,
            })
        if is_paid:
            if local >= week_start:
                week_revenue += float(o.total or 0)
            elif local >= prev_week_start:
                prev_week_revenue += float(o.total or 0)
            if local >= month_start:
                month_revenue += float(o.total or 0)

    # Почасовое распределение — отдаём только рабочие часы (8-22 обычно
    # достаточно для флориста, но даём весь день, фронт сам решит).
    hours = [{"hour": h, "count": hourly[h]} for h in range(24)]

    # Источники заказов: канал из связанной conversation→customer.channel.
    # Делаем отдельный SQL — быстрее, чем ходить по relationship для каждого.
    channel_rows = (
        db.query(models.Customer.channel, func.count(models.Order.id))
        .join(models.Order, models.Order.customer_id == models.Customer.id)
        .filter(models.Order.shop_id == shop.id)
        .group_by(models.Customer.channel)
        .all()
    )
    for ch, cnt in channel_rows:
        by_channel[(ch or "other") or "other"] = int(cnt)

    # Диалоги, требующие менеджера (handoff) — для блока «нужен ты».
    handoff_count = (
        db.query(func.count(models.Conversation.id))
        .filter_by(shop_id=shop.id, status="handoff")
        .scalar() or 0
    )
    pending_payment_count = (
        db.query(func.count(models.Conversation.id))
        .filter_by(shop_id=shop.id, status="pending_payment")
        .scalar() or 0
    )
    active_conv_count = (
        db.query(func.count(models.Conversation.id))
        .filter_by(shop_id=shop.id, status="active")
        .scalar() or 0
    )

    # Сравнение неделя к неделе.
    if prev_week_revenue > 0:
        week_change_pct = round(
            (week_revenue - prev_week_revenue) / prev_week_revenue * 100, 1
        )
    elif week_revenue > 0:
        week_change_pct = 100.0
    else:
        week_change_pct = 0.0

    # Топ-3 товара по выручке за месяц.
    top_products: dict[str, dict] = {}
    for o in orders:
        if o.status not in PAID_STATUSES:
            continue
        created = _to_aware_utc(o.created_at)
        if not created or created.astimezone(tz) < month_start:
            continue
        for it in (o.items or []):
            name = (it.get("name") or "").strip()
            if not name:
                continue
            qty = int(it.get("qty") or 1)
            price = float(it.get("price") or 0)
            entry = top_products.setdefault(name, {"name": name, "qty": 0, "revenue": 0.0})
            entry["qty"] += qty
            entry["revenue"] += qty * price
    top_products_list = sorted(
        top_products.values(), key=lambda x: x["revenue"], reverse=True
    )[:3]

    return {
        "currency": shop.currency or "RUB",
        "today": {
            "revenue": round(today_revenue, 2),
            "orders": today_orders,
            "paid_orders": today_paid_orders,
            "hours": hours,
            "orders_list": sorted(
                today_orders_list, key=lambda x: x["created_at"], reverse=True
            ),
        },
        "week": {
            "revenue": round(week_revenue, 2),
            "change_pct": week_change_pct,
        },
        "month": {
            "revenue": round(month_revenue, 2),
        },
        "pipeline": pipeline,
        "by_channel": by_channel,
        "conversations": {
            "handoff": int(handoff_count),
            "pending_payment": int(pending_payment_count),
            "active": int(active_conv_count),
        },
        "top_products": top_products_list,
        "now": now_local.isoformat(),
    }


@router.get("/report")
def report(
    days: int = 30,
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    """Расширенная аналитика для дашборда: воронка, выручка по дням,
    часы пик, топ-букеты и доля AI vs ручное ведение диалога."""
    days = max(7, min(days, 90))
    tz = _shop_tz(shop)
    now_local = datetime.now(tz)
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    period_start = today_start - timedelta(days=days - 1)

    orders: list[models.Order] = db.query(models.Order).filter_by(shop_id=shop.id).all()

    # Воронка: диалоги → счета → оплаты (за период).
    convs = db.query(models.Conversation).filter_by(shop_id=shop.id).all()
    dialogs = 0
    for c in convs:
        created = _to_aware_utc(c.created_at)
        if created and created.astimezone(tz) >= period_start:
            dialogs += 1

    # Выручка по дням + часы пик + счета/оплаты за период.
    day_labels = [(period_start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    revenue_by_day = {d: 0.0 for d in day_labels}
    orders_by_day = {d: 0 for d in day_labels}
    hourly = [0] * 24
    invoices = 0
    paid = 0
    convs_with_invoice: set[int] = set()
    convs_with_paid: set[int] = set()
    top: dict[str, dict] = {}

    for o in orders:
        created = _to_aware_utc(o.created_at)
        if not created:
            continue
        local = created.astimezone(tz)
        if local < period_start:
            continue
        invoices += 1
        if o.conversation_id:
            convs_with_invoice.add(o.conversation_id)
        key = local.strftime("%Y-%m-%d")
        orders_by_day[key] = orders_by_day.get(key, 0) + 1
        hourly[local.hour] += 1
        if o.status in PAID_STATUSES:
            paid += 1
            if o.conversation_id:
                convs_with_paid.add(o.conversation_id)
            revenue_by_day[key] = revenue_by_day.get(key, 0.0) + float(o.total or 0)
            for it in (o.items or []):
                name = (it.get("name") or "").strip()
                if not name:
                    continue
                qty = int(it.get("qty") or 1)
                price = float(it.get("price") or 0)
                entry = top.setdefault(name, {"name": name, "qty": 0, "revenue": 0.0})
                entry["qty"] += qty
                entry["revenue"] += qty * price

    # AI vs ручное: сколько диалогов потребовало менеджера (handoff) за период.
    handoff_dialogs = 0
    for c in convs:
        created = _to_aware_utc(c.created_at)
        if created and created.astimezone(tz) >= period_start and c.status == "handoff":
            handoff_dialogs += 1
    ai_dialogs = max(dialogs - handoff_dialogs, 0)

    def _pct(part: int, whole: int) -> float:
        return round(part / whole * 100, 1) if whole else 0.0

    return {
        "currency": shop.currency or "RUB",
        "days": days,
        "funnel": {
            "dialogs": dialogs,
            "invoiced": len(convs_with_invoice),
            "paid": len(convs_with_paid),
            "invoice_rate": _pct(len(convs_with_invoice), dialogs),
            "paid_rate": _pct(len(convs_with_paid), dialogs),
        },
        "totals": {"invoices": invoices, "paid_orders": paid,
                   "revenue": round(sum(revenue_by_day.values()), 2)},
        "revenue_by_day": [
            {"date": d, "revenue": round(revenue_by_day[d], 2), "orders": orders_by_day[d]}
            for d in day_labels
        ],
        "peak_hours": [{"hour": h, "count": hourly[h]} for h in range(24)],
        "top_products": sorted(top.values(), key=lambda x: x["revenue"], reverse=True)[:5],
        "ai_vs_manual": {"ai": ai_dialogs, "manual": handoff_dialogs,
                         "ai_pct": _pct(ai_dialogs, dialogs)},
        "now": now_local.isoformat(),
    }
