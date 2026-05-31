"""Inbox: persist + retry для входящих сообщений."""
import hashlib
import hmac
import json
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import models
from app.config import settings
from app.database import SessionLocal
from app.dispatcher import persist_incoming, retry_pending_inbox
from app.main import app

client = TestClient(app)


def _sign(body: bytes, ts: str | None = None) -> dict:
    ts = ts or str(int(time.time()))
    mac = hmac.new(
        settings.wa_bridge_secret.encode("utf-8"),
        ts.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return {"X-Bridge-Signature": mac, "X-Bridge-Timestamp": ts}


def _make_shop_with_flow() -> int:
    """Создаём магазин + один активный flow, чтобы dispatcher мог завести conversation."""
    db = SessionLocal()
    try:
        shop = models.Shop(email=f"inbox-{time.time_ns()}@t.t", password_hash="x", name="T")
        db.add(shop)
        db.flush()
        flow = models.Flow(shop_id=shop.id, name="default", is_active=True, graph={
            "nodes": [{"id": "n1", "data": {"kind": "agent"}}],
            "edges": [],
        })
        db.add(flow)
        db.commit()
        return shop.id
    finally:
        db.close()


def test_persist_incoming_creates_pending_row():
    shop_id = _make_shop_with_flow()
    inbox_id = persist_incoming(shop_id, "whatsapp", "77001112233", "привет", "Aleks")
    assert inbox_id

    db = SessionLocal()
    try:
        row = db.get(models.IncomingMessage, inbox_id)
        assert row is not None
        assert row.status == "pending"
        assert row.shop_id == shop_id
        assert row.text == "привет"
        assert row.attempts == 0
        assert row.processed_at is None
    finally:
        db.close()


def test_webhook_persists_inbox_before_processing():
    """POST на webhook должен синхронно создать IncomingMessage до фоновой обработки."""
    shop_id = _make_shop_with_flow()
    body = json.dumps({
        "event": "message",
        "shop_id": shop_id,
        "from": "77002223344",
        "text": "тестовое сообщение",
        "name": "Customer",
    }).encode()
    headers = {"Content-Type": "application/json", **_sign(body)}

    # Перехватываем handle_incoming, чтобы убедиться, что inbox создан ДО его вызова.
    captured: dict = {}

    def _fake_handle(shop_id_, channel, ext, text, name, inbox_id=None):
        captured.update({"inbox_id": inbox_id, "shop_id": shop_id_, "text": text})
        return None

    with patch("app.routers.channels.handle_incoming", side_effect=_fake_handle):
        r = client.post("/api/channels/whatsapp/webhook", content=body, headers=headers)
    assert r.status_code == 200

    assert captured.get("inbox_id"), "handle_incoming must receive inbox_id from webhook"

    db = SessionLocal()
    try:
        row = db.get(models.IncomingMessage, captured["inbox_id"])
        assert row is not None
        assert row.shop_id == shop_id
        assert row.channel == "whatsapp"
        assert row.text == "тестовое сообщение"
    finally:
        db.close()


def test_retry_pending_inbox_processes_orphans():
    """Pending-записи без обработки должны подбираться retry-job'ом."""
    shop_id = _make_shop_with_flow()
    inbox_id = persist_incoming(shop_id, "sim", "u-1", "hi", "U")
    assert inbox_id

    sent = retry_pending_inbox()
    assert sent >= 1

    db = SessionLocal()
    try:
        row = db.get(models.IncomingMessage, inbox_id)
        # Любая обработка (успех или фейл) должна изменить статус с pending или поднять attempts.
        assert row.status in {"processed", "pending", "failed"}
        assert row.attempts >= 1
    finally:
        db.close()


def test_retry_skips_exhausted_attempts():
    """Записи с attempts >= max_attempts не должны вытаскиваться."""
    shop_id = _make_shop_with_flow()
    db = SessionLocal()
    try:
        row = models.IncomingMessage(
            shop_id=shop_id, channel="sim", external_id="u-x",
            text="x", status="pending", attempts=5,
        )
        db.add(row)
        db.commit()
        rid = row.id
    finally:
        db.close()

    sent = retry_pending_inbox(max_attempts=5)
    # Эта запись не должна быть подобрана.
    db = SessionLocal()
    try:
        row = db.get(models.IncomingMessage, rid)
        assert row.attempts == 5
        assert row.status == "pending"
    finally:
        db.close()
