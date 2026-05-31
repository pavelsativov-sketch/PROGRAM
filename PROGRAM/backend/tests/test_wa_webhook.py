"""WA webhook: HMAC + timestamp защита от replay."""
import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from app.config import settings
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


def _body(**overrides) -> bytes:
    base = {"event": "ready", "shop_id": 99999, "me": "0000"}
    base.update(overrides)
    return json.dumps(base).encode()


def test_wa_webhook_valid_signature_ok():
    body = _body()
    r = client.post("/api/channels/whatsapp/webhook", content=body, headers={
        "Content-Type": "application/json",
        **_sign(body),
    })
    # shop 99999 не существует — backend всё равно вернёт 200 для event=ready, просто no-op.
    assert r.status_code == 200


def test_wa_webhook_wrong_signature_rejected():
    body = _body()
    r = client.post("/api/channels/whatsapp/webhook", content=body, headers={
        "Content-Type": "application/json",
        "X-Bridge-Signature": "0" * 64,
        "X-Bridge-Timestamp": str(int(time.time())),
    })
    assert r.status_code == 401


def test_wa_webhook_old_timestamp_rejected_when_no_legacy():
    """Слишком старый timestamp + правильная новая подпись = реджект.
    В test-режиме legacy fallback включён, поэтому подпись по чистому body всё ещё может пройти.
    Здесь специально портим body, чтобы legacy fallback тоже не сработал.
    """
    body = _body()
    old_ts = str(int(time.time()) - settings.wa_webhook_max_skew - 100)
    sig_for_old = hmac.new(
        settings.wa_bridge_secret.encode("utf-8"),
        old_ts.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    r = client.post("/api/channels/whatsapp/webhook", content=body, headers={
        "Content-Type": "application/json",
        "X-Bridge-Signature": sig_for_old,
        "X-Bridge-Timestamp": old_ts,
    })
    # Новый формат отклоняем (skew); legacy fallback по чистому body тоже не подойдёт
    # (sig_for_old подписан с timestamp prefix).
    assert r.status_code == 401


def test_wa_webhook_no_auth_rejected():
    body = _body()
    r = client.post("/api/channels/whatsapp/webhook", content=body, headers={
        "Content-Type": "application/json",
    })
    assert r.status_code == 401
