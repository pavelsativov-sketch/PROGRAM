"""Audit: чувствительные значения не должны попадать в meta."""
import json

from app import models
from app.audit import log_action, sanitize_meta
from app.database import SessionLocal


def test_sanitize_redacts_known_sensitive_keys():
    raw = {
        "ai_api_key": "sk-secret-12345",
        "openai_api_key": "very-long-real-key",
        "password": "hunter2",
        "wa_bridge_secret": "shhh",
        "ig_proxy": "http://user:pass@proxy:1080",
        "Authorization": "Bearer xyz",
        "cookie": "session=abc",
        "fields": ["ai_api_key", "name"],          # значение — список строк, не секрет
        "ai_key_changed": True,                    # булев флаг — оставляем
        "name_changed": False,                     # тоже флаг
        "shop_id": 42,                             # обычное поле
    }
    clean = sanitize_meta(raw)
    # Секретные значения затёрты.
    for k in ("ai_api_key", "openai_api_key", "password", "wa_bridge_secret",
              "ig_proxy", "Authorization", "cookie"):
        assert clean[k] == "***redacted***", f"{k} must be redacted, got {clean[k]!r}"
    # Булевы флаги сохранены as-is.
    assert clean["ai_key_changed"] is True
    assert clean["name_changed"] is False
    # Обычные поля сохранены.
    assert clean["fields"] == ["ai_api_key", "name"]
    assert clean["shop_id"] == 42


def test_sanitize_recurses_into_nested_dicts():
    raw = {"outer": {"api_key": "leak", "ok": "fine"}}
    clean = sanitize_meta(raw)
    assert clean["outer"]["api_key"] == "***redacted***"
    assert clean["outer"]["ok"] == "fine"


def test_log_action_persists_sanitized_meta():
    db = SessionLocal()
    try:
        log_action(
            db,
            "test_secret_leak_check",
            shop_id=None,
            meta={"ai_api_key": "sk-NOT-LEAKED-EVER", "ai_key_changed": True},
        )
        row = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == "test_secret_leak_check")
            .order_by(models.AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert "sk-NOT-LEAKED-EVER" not in json.dumps(row.meta or {})
        assert row.meta.get("ai_api_key") == "***redacted***"
        assert row.meta.get("ai_key_changed") is True
    finally:
        db.close()


def test_sanitize_none_and_empty():
    assert sanitize_meta(None) == {}
    assert sanitize_meta({}) == {}
