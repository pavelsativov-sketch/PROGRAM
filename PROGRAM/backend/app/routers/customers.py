"""CRM-роутер: список клиентов, карточка с историей заказов и заметками."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..audit import log_action
from ..auth import current_shop
from ..database import get_db

router = APIRouter(prefix="/api/customers", tags=["customers"])

PAID_STATUSES = ("paid", "delivered")


def _to_aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _own(db: Session, shop: models.Shop, cid: int) -> models.Customer:
    c = db.get(models.Customer, cid)
    if not c or c.shop_id != shop.id:
        raise HTTPException(404, "Клиент не найден")
    return c


@router.get("")
def list_customers(
    q: str | None = None,
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    """Список клиентов магазина с агрегатом: число заказов, LTV, дата последнего заказа."""
    base = db.query(models.Customer).filter_by(shop_id=shop.id)
    if q:
        like = f"%{q.lower()}%"
        base = base.filter(
            (func.lower(models.Customer.name).like(like))
            | (func.lower(models.Customer.external_id).like(like))
        )
    customers = base.order_by(models.Customer.id.desc()).limit(500).all()

    # Считаем агрегаты пакетно, чтобы не делать N+1 при больших списках.
    cust_ids = [c.id for c in customers]
    agg: dict[int, dict] = {cid: {"orders": 0, "ltv": 0.0, "last_order_at": None} for cid in cust_ids}
    if cust_ids:
        rows = (
            db.query(
                models.Order.customer_id,
                func.count(models.Order.id),
                func.sum(models.Order.total),
                func.max(models.Order.created_at),
            )
            .filter(
                models.Order.shop_id == shop.id,
                models.Order.customer_id.in_(cust_ids),
            )
            .group_by(models.Order.customer_id)
            .all()
        )
        for cid, n, total, last_at in rows:
            agg[cid] = {
                "orders": int(n or 0),
                "ltv": float(total or 0),
                "last_order_at": _to_aware_utc(last_at).isoformat() if last_at else None,
            }
    out = []
    for c in customers:
        a = agg.get(c.id, {})
        out.append({
            "id": c.id,
            "name": c.name or "",
            "channel": c.channel or "",
            "external_id": c.external_id or "",
            "tags": list(c.tags or []),
            "orders": a.get("orders", 0),
            "ltv": round(a.get("ltv", 0.0), 2),
            "last_order_at": a.get("last_order_at"),
        })
    return out


@router.get("/{cid}")
def get_customer(
    cid: int,
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    c = _own(db, shop, cid)
    orders = (
        db.query(models.Order)
        .filter_by(shop_id=shop.id, customer_id=cid)
        .order_by(models.Order.created_at.desc())
        .all()
    )
    convs = (
        db.query(models.Conversation)
        .filter_by(shop_id=shop.id, customer_id=cid)
        .order_by(models.Conversation.updated_at.desc())
        .all()
    )
    ltv = sum(float(o.total or 0) for o in orders if o.status in PAID_STATUSES)
    paid_count = sum(1 for o in orders if o.status in PAID_STATUSES)

    return {
        "id": c.id,
        "name": c.name or "",
        "channel": c.channel or "",
        "external_id": c.external_id or "",
        "tags": list(c.tags or []),
        "notes": c.notes or "",
        "important_dates": list(c.important_dates or []),
        "created_at": _to_aware_utc(c.created_at).isoformat() if c.created_at else None,
        "stats": {
            "orders_count": len(orders),
            "paid_orders": paid_count,
            "ltv": round(ltv, 2),
        },
        "orders": [
            {
                "id": o.id,
                "status": o.status,
                "total": float(o.total or 0),
                "items": o.items or [],
                "details": o.details or {},
                "created_at": _to_aware_utc(o.created_at).isoformat() if o.created_at else None,
            }
            for o in orders
        ],
        "conversations": [
            {
                "id": cv.id,
                "status": cv.status,
                "updated_at": _to_aware_utc(cv.updated_at).isoformat() if cv.updated_at else None,
            }
            for cv in convs
        ],
    }


class CustomerPatch(BaseModel):
    name: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    important_dates: list[dict] | None = None


@router.put("/{cid}")
def update_customer(
    request: Request,
    cid: int,
    payload: CustomerPatch,
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    c = _own(db, shop, cid)
    data = payload.model_dump(exclude_unset=True)
    if "tags" in data:
        # нормализуем теги: убираем пустые, дубликаты, обрезаем длину
        cleaned: list[str] = []
        seen: set[str] = set()
        for t in data["tags"] or []:
            t = (str(t) or "").strip()[:32]
            if not t:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(t)
        data["tags"] = cleaned[:20]
    if "important_dates" in data:
        # Нормализуем важные даты: label + date(YYYY-MM-DD) + recurring(bool).
        norm: list[dict] = []
        for item in (data["important_dates"] or []):
            if not isinstance(item, dict):
                continue
            date = (str(item.get("date") or "")).strip()[:10]
            if not date:
                continue
            norm.append({
                "label": (str(item.get("label") or "")).strip()[:64] or "Важная дата",
                "date": date,
                "recurring": bool(item.get("recurring", True)),
            })
        data["important_dates"] = norm[:20]
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    log_action(db, "customer_update", shop_id=shop.id, request=request,
               meta={"customer_id": cid, "fields": list(data.keys())})
    return {
        "id": c.id,
        "name": c.name or "",
        "tags": list(c.tags or []),
        "notes": c.notes or "",
        "important_dates": list(c.important_dates or []),
    }
