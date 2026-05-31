import time

from app.config import settings


def test_pay_token_roundtrip_with_exp():
    t = settings.sign_pay_token(order_id=42, shop_id=1)
    assert settings.verify_pay_token(42, 1, t) is True
    # Чужой order/shop — отвергаем.
    assert settings.verify_pay_token(43, 1, t) is False
    assert settings.verify_pay_token(42, 2, t) is False


def test_pay_token_expired():
    t = settings.sign_pay_token(order_id=42, shop_id=1, exp_ts=int(time.time()) - 10)
    assert settings.verify_pay_token(42, 1, t) is False


def test_pay_token_tampered():
    t = settings.sign_pay_token(order_id=42, shop_id=1)
    # Сломаем подпись.
    bad = t[:-1] + ("0" if t[-1] != "0" else "1")
    assert settings.verify_pay_token(42, 1, bad) is False


def test_pay_token_legacy_format_accepted_in_dev():
    # Legacy 32-hex без точки — принимается только не в prod.
    # ENV=test в тестах, так что должно работать.
    import hashlib
    import hmac
    msg = b"1:42"
    legacy = hmac.new(settings.pay_signing_key, msg, hashlib.sha256).hexdigest()[:32]
    assert settings.verify_pay_token(42, 1, legacy) is True


def test_pay_token_empty():
    assert settings.verify_pay_token(1, 1, "") is False
    assert settings.verify_pay_token(1, 1, "garbage") is False


def test_pay_token_legacy_rejected_in_prod(monkeypatch):
    """В prod legacy-формат без exp обязан отклоняться, даже если подпись валидна."""
    import hashlib
    import hmac
    msg = b"1:42"
    legacy = hmac.new(settings.pay_signing_key, msg, hashlib.sha256).hexdigest()[:32]
    monkeypatch.setattr(settings, "env", "prod")
    assert settings.verify_pay_token(42, 1, legacy) is False


def test_pay_token_malformed_exp_hex():
    """Не-hex значение в exp-секции должно отдать False, не падать."""
    assert settings.verify_pay_token(42, 1, "zzz.abcdef") is False
    assert settings.verify_pay_token(42, 1, ".abcdef") is False
    assert settings.verify_pay_token(42, 1, "ff.") is False


def test_pay_confirm_rejects_without_token():
    """POST /pay/{id}/confirm без подписи → 404 (не 200/500)."""
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/pay/1/confirm")
    assert r.status_code == 404
    r2 = c.post("/pay/1/confirm?t=garbage")
    assert r2.status_code == 404
