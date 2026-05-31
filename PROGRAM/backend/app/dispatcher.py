"""Маршрутизация входящих сообщений по магазинам."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal
from .flow_engine import run_conversation
from .locks import advisory_lock

log = logging.getLogger(__name__)


def persist_incoming(
    shop_id: int, channel: str, external_id: str, text: str, name: str = ""
) -> int | None:
    """Синхронно сохраняем входящее сообщение в inbox. Возвращаем его id.

    Должно вызываться из webhook'а ДО постановки задачи в фон, чтобы при крэше
    backend между ACK и обработкой сообщение не было потеряно.
    """
    db: Session = SessionLocal()
    try:
        row = models.IncomingMessage(
            shop_id=shop_id,
            channel=channel,
            external_id=external_id,
            customer_name=name or "",
            text=text or "",
            status="pending",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    except Exception:
        log.exception("persist_incoming failed shop=%s ch=%s ext=%s", shop_id, channel, external_id)
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()


def _mark_processed(inbox_id: int | None, error: str = "") -> None:
    if not inbox_id:
        return
    db: Session = SessionLocal()
    try:
        row = db.get(models.IncomingMessage, inbox_id)
        if not row:
            return
        row.attempts = (row.attempts or 0) + 1
        if error:
            row.status = "failed" if row.attempts >= 5 else "pending"
            row.last_error = error[:512]
        else:
            row.status = "processed"
            row.processed_at = datetime.now(UTC)
            row.last_error = ""
        db.commit()
    except Exception:
        log.exception("mark_processed failed inbox_id=%s", inbox_id)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _active_flow(db: Session, shop_id: int) -> models.Flow | None:
    return (
        db.query(models.Flow)
        .filter(models.Flow.shop_id == shop_id, models.Flow.is_active == True)  # noqa: E712
        .order_by(models.Flow.id.desc())
        .first()
    )


def handle_incoming(
    shop_id: int,
    channel: str,
    external_id: str,
    text: str,
    name: str = "",
    inbox_id: int | None = None,
) -> int | None:
    """Сериализуем обработку одного клиента — иначе пачка сообщений ломает state-машину.
    Используем advisory_lock (Redis или process-local в зависимости от настроек).

    Если передан inbox_id — отмечаем запись inbox как processed/failed после обработки.
    """
    key = f"conv:{shop_id}:{channel}:{external_id}"
    err = ""
    try:
        with advisory_lock(key):
            return _handle_incoming_locked(shop_id, channel, external_id, text, name)
    except Exception as e:
        err = str(e) or e.__class__.__name__
        log.exception("handle_incoming top-level failed shop=%s ch=%s", shop_id, channel)
        return None
    finally:
        _mark_processed(inbox_id, error=err)


def retry_pending_inbox(max_attempts: int = 5, batch: int = 50) -> int:
    """Повторно отправляет в обработку pending-записи (за вычетом тех, у кого
    attempts >= max_attempts). Возвращает кол-во отправленных задач."""
    db: Session = SessionLocal()
    sent = 0
    try:
        rows = (
            db.query(models.IncomingMessage)
            .filter(models.IncomingMessage.status == "pending")
            .filter(models.IncomingMessage.attempts < max_attempts)
            .order_by(models.IncomingMessage.id.asc())
            .limit(batch)
            .all()
        )
        for r in rows:
            log.info("retry_pending_inbox: re-dispatching inbox_id=%s shop=%s ch=%s",
                     r.id, r.shop_id, r.channel)
            try:
                handle_incoming(r.shop_id, r.channel, r.external_id, r.text, r.customer_name or "", inbox_id=r.id)
                sent += 1
            except Exception:
                log.exception("retry_pending_inbox: handle_incoming failed inbox_id=%s", r.id)
        return sent
    except Exception:
        log.exception("retry_pending_inbox query failed")
        return sent
    finally:
        db.close()


def _handle_incoming_locked(shop_id: int, channel: str, external_id: str, text: str, name: str) -> int | None:
    log.info("incoming shop=%s ch=%s ext=%s text=%r", shop_id, channel, external_id, (text or "")[:120])
    db: Session = SessionLocal()
    try:
        shop = db.get(models.Shop, shop_id)
        if not shop:
            log.warning("incoming: shop %s not found", shop_id)
            return None

        cust = (
            db.query(models.Customer)
            .filter_by(shop_id=shop_id, channel=channel, external_id=external_id)
            .first()
        )
        if not cust:
            cust = models.Customer(shop_id=shop_id, channel=channel, external_id=external_id, name=name or "")
            db.add(cust)
            db.flush()
        elif name and not cust.name:
            cust.name = name

        conv = (
            db.query(models.Conversation)
            .filter(
                models.Conversation.shop_id == shop_id,
                models.Conversation.customer_id == cust.id,
                models.Conversation.status.in_(["active", "pending_payment", "payment_review", "handoff"]),
            )
            .order_by(models.Conversation.id.desc())
            .first()
        )
        if not conv:
            flow = _active_flow(db, shop_id)
            if not flow:
                log.warning("incoming: no active flow for shop %s — bot не ответит. Активируйте флоу в UI.", shop_id)
                return None
            log.info("incoming: starting new conversation for shop=%s flow=%s", shop_id, flow.id)
            conv = models.Conversation(
                shop_id=shop_id, customer_id=cust.id, flow_id=flow.id,
                variables={}, status="active",
            )
            db.add(conv)
            db.flush()

        # Если диалог уже забрал менеджер — AI молчит, просто сохраняем сообщение клиента.
        if conv.status == "handoff":
            db.add(models.Message(conversation_id=conv.id, role="user", text=text))
            db.commit()
            log.info("incoming: conv %s in handoff — AI silent", conv.id)
            return conv.id

        run_conversation(db, shop, conv, text)

        # Outbox: пытаемся доставить ВСЕ ещё не доставленные bot-сообщения этого диалога
        # (включая зависшие с предыдущих попыток, когда канал был недоступен).
        to_send = [m for m in conv.messages if m.role == "bot" and not (m.meta or {}).get("sent")]
        log.info("incoming: %d bot reply(ies) to deliver (incl. retries)", len(to_send))
        for m in to_send:
            ok = _deliver(shop_id, channel, external_id, m.text)
            meta = dict(m.meta or {})
            meta["sent"] = bool(ok)
            if ok:
                meta.pop("send_error", None)
                meta["attempts"] = int(meta.get("attempts", 0)) + 1
            else:
                meta["send_error"] = True
                meta["attempts"] = int(meta.get("attempts", 0)) + 1
                log.warning("incoming: bot reply NOT delivered shop=%s ch=%s ext=%s msg_id=%s attempts=%s",
                            shop_id, channel, external_id, m.id, meta["attempts"])
            m.meta = meta

        db.commit()
        return conv.id
    except Exception:
        log.exception("handle_incoming failed shop=%s channel=%s ext=%s", shop_id, channel, external_id)
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()


def _deliver(shop_id: int, channel: str, external_id: str, text: str) -> bool:
    try:
        if channel == "whatsapp":
            from .channels.whatsapp import whatsapp
            r = whatsapp.send(shop_id, external_id, text)
            return bool(r.get("ok", False)) or bool(r.get("id"))
        if channel == "instagram":
            from .channels.instagram import ig_manager
            r = ig_manager.get(shop_id).send(external_id, text)
            return bool(r.get("ok", False))
        if channel == "sim":
            return True
    except Exception:
        log.exception("deliver failed channel=%s shop=%s", channel, shop_id)
    return False
