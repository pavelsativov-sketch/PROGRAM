import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import log_action
from ..auth import current_shop
from ..config import settings
from ..database import get_db
from ..flow_engine import run_conversation
from ..rate_limit import limiter

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
def list_conv(
    status: str | None = None,
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    q = db.query(models.Conversation).filter_by(shop_id=shop.id)
    if status:
        q = q.filter(models.Conversation.status == status)
    convs = q.order_by(models.Conversation.updated_at.desc(), models.Conversation.id.desc()).all()
    out = []
    for c in convs:
        last = c.messages[-1] if c.messages else None
        cust = c.customer
        out.append({
            "id": c.id,
            "status": c.status,
            "flow_id": c.flow_id,
            "updated_at": c.updated_at,
            "customer": {
                "id": cust.id if cust else None,
                "name": (cust.name if cust else "") or "",
                "channel": cust.channel if cust else "",
                "external_id": cust.external_id if cust else "",
            } if cust else None,
            "last_message": {
                "role": last.role,
                "text": (last.text or "")[:120],
                "created_at": last.created_at,
            } if last else None,
            "unread_for_manager": c.status == "handoff",
        })
    return out


@router.get("/{cid}")
def get_conv(cid: int, db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    c = db.get(models.Conversation, cid)
    if not c or c.shop_id != shop.id:
        raise HTTPException(404)
    return {
        "id": c.id,
        "customer": {"id": c.customer.id, "name": c.customer.name, "channel": c.customer.channel, "external_id": c.customer.external_id} if c.customer else None,
        "flow_id": c.flow_id,
        "current_node_id": c.current_node_id,
        "variables": c.variables,
        "status": c.status,
        "messages": [{"id": m.id, "role": m.role, "text": m.text, "created_at": m.created_at} for m in c.messages],
    }


@router.post("/sim")
@limiter.limit(settings.rate_limit_sim)
def simulate(
    request: Request,
    payload: schemas.SimMessageIn,
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    cust = db.query(models.Customer).filter_by(shop_id=shop.id, channel="sim", external_id=payload.external_id).first()
    if not cust:
        cust = models.Customer(shop_id=shop.id, channel="sim", external_id=payload.external_id, name="Симулятор")
        db.add(cust); db.flush()

    conv = None
    if payload.conversation_id:
        c = db.get(models.Conversation, payload.conversation_id)
        if c and c.shop_id == shop.id:
            conv = c
    if not conv:
        flow_id = payload.flow_id
        if not flow_id:
            fl = db.query(models.Flow).filter_by(shop_id=shop.id, is_active=True).order_by(models.Flow.id.desc()).first()
            if not fl:
                raise HTTPException(400, "Нет активного сценария")
            flow_id = fl.id
        conv = models.Conversation(shop_id=shop.id, customer_id=cust.id, flow_id=flow_id, variables={}, status="active")
        db.add(conv); db.flush()

    run_conversation(db, shop, conv, payload.text)
    for m in conv.messages:
        if m.role == "bot" and not (m.meta or {}).get("sent"):
            m.meta = {**(m.meta or {}), "sent": True}
    db.commit()
    # Для симулятора-дебаггера отдаём ещё и активный узел графа, чтобы
    # фронт мог подсветить «где сейчас находится диалог».
    return {
        "conversation_id": conv.id,
        "messages": [{"id": m.id, "role": m.role, "text": m.text} for m in conv.messages],
        "variables": conv.variables,
        "status": conv.status,
        "current_node_id": conv.current_node_id or "",
        "flow_id": conv.flow_id,
    }


def _own_conv(db: Session, shop: models.Shop, cid: int) -> models.Conversation:
    c = db.get(models.Conversation, cid)
    if not c or c.shop_id != shop.id:
        raise HTTPException(404)
    return c


@router.post("/{cid}/takeover")
def takeover(
    request: Request,
    cid: int,
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    """Менеджер забирает диалог себе — AI больше не отвечает в этом диалоге."""
    c = _own_conv(db, shop, cid)
    c.status = "handoff"
    db.commit()
    log_action(db, "conv_takeover", shop_id=shop.id, request=request, meta={"conv_id": cid})
    return {"ok": True, "status": c.status}


@router.post("/{cid}/resume")
def resume(
    request: Request,
    cid: int,
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    """Возвращает диалог под управление AI."""
    c = _own_conv(db, shop, cid)
    c.status = "active"
    db.commit()
    log_action(db, "conv_resume", shop_id=shop.id, request=request, meta={"conv_id": cid})
    return {"ok": True, "status": c.status}


@router.post("/{cid}/reply")
def manager_reply(
    request: Request,
    cid: int,
    payload: schemas.ManagerReplyIn,
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    """Менеджер пишет клиенту вручную. Сообщение уходит по тому же каналу, что и диалог."""
    c = _own_conv(db, shop, cid)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(400, "Пустое сообщение")

    # Если ещё не в handoff — автоматически переводим, чтобы AI не вмешивался.
    if c.status != "handoff":
        c.status = "handoff"

    # Доставляем по нужному каналу
    delivered = False
    cust = c.customer
    channel = cust.channel if cust else ""
    ext_id = cust.external_id if cust else ""
    try:
        if channel == "whatsapp":
            from ..channels.whatsapp import whatsapp
            r = whatsapp.send(shop.id, ext_id, text)
            delivered = bool(r.get("ok", False)) or bool(r.get("id"))
        elif channel == "instagram":
            from ..channels.instagram import ig_manager
            r = ig_manager.get(shop.id).send(ext_id, text)
            delivered = bool(r.get("ok", False))
        elif channel == "sim":
            delivered = True
    except Exception:
        log.exception("manager_reply deliver failed cid=%s ch=%s", cid, channel)

    msg = models.Message(
        conversation_id=c.id,
        role="bot",
        text=text,
        meta={"manager": True, "sent": delivered, "send_error": (not delivered) and channel != ""},
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    log_action(db, "manager_reply", shop_id=shop.id, request=request,
               meta={"conv_id": cid, "delivered": delivered, "channel": channel})
    return {
        "ok": True,
        "delivered": delivered,
        "status": c.status,
        "message": {"id": msg.id, "role": msg.role, "text": msg.text, "meta": msg.meta},
    }
