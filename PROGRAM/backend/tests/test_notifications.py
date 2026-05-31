"""Тесты центра уведомлений, мониторинга и проактивных напоминаний."""
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app import models, monitoring, notifications
from app.database import SessionLocal
from app.main import app

client = TestClient(app)


def _signup(email, name="Shop"):
    r = client.post("/api/auth/signup", json={"email": email, "password": "password1!", "name": name})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _shop(email):
    db = SessionLocal()
    try:
        return db.query(models.Shop).filter_by(email=email).first()
    finally:
        db.close()


# ---------- Центр уведомлений: фид + чтение + изоляция ----------

def test_notification_feed_and_read():
    token = _signup("notif1@example.com")
    db = SessionLocal()
    try:
        shop = db.query(models.Shop).filter_by(email="notif1@example.com").first()
        notifications.record(db, shop, type="bot_down", severity="critical",
                             title="Бот офлайн", body="canal down", telegram=False)
        db.commit()
    finally:
        db.close()

    r = client.get("/api/notifications", headers=_h(token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["unread_count"] == 1
    assert len(data["items"]) == 1
    nid = data["items"][0]["id"]
    assert data["items"][0]["is_read"] is False

    assert client.post(f"/api/notifications/{nid}/read", headers=_h(token)).status_code == 200
    assert client.get("/api/notifications/unread-count", headers=_h(token)).json()["count"] == 0

    # delete
    assert client.delete(f"/api/notifications/{nid}", headers=_h(token)).status_code == 200
    assert client.get("/api/notifications", headers=_h(token)).json()["items"] == []


def test_notifications_isolated_per_shop():
    ta = _signup("niso-a@example.com")
    tb = _signup("niso-b@example.com")
    db = SessionLocal()
    try:
        shop_a = db.query(models.Shop).filter_by(email="niso-a@example.com").first()
        notifications.record(db, shop_a, type="handoff", title="A only", telegram=False)
        db.commit()
    finally:
        db.close()
    assert client.get("/api/notifications", headers=_h(ta)).json()["unread_count"] == 1
    assert client.get("/api/notifications", headers=_h(tb)).json()["unread_count"] == 0


def test_read_all():
    token = _signup("readall@example.com")
    db = SessionLocal()
    try:
        shop = db.query(models.Shop).filter_by(email="readall@example.com").first()
        for i in range(3):
            notifications.record(db, shop, type="reminder", title=f"n{i}", telegram=False)
        db.commit()
    finally:
        db.close()
    assert client.get("/api/notifications/unread-count", headers=_h(token)).json()["count"] == 3
    r = client.post("/api/notifications/read-all", headers=_h(token))
    assert r.json()["updated"] == 3
    assert client.get("/api/notifications/unread-count", headers=_h(token)).json()["count"] == 0


# ---------- Анти-спам (dedup) ----------

def test_dedup_window_blocks_repeat():
    _signup("dedup@example.com")
    db = SessionLocal()
    try:
        shop = db.query(models.Shop).filter_by(email="dedup@example.com").first()
        n1 = notifications.record(db, shop, type="bot_idle", title="idle",
                                  dedup_key="bot_idle", dedup_window=timedelta(hours=12), telegram=False)
        n2 = notifications.record(db, shop, type="bot_idle", title="idle",
                                  dedup_key="bot_idle", dedup_window=timedelta(hours=12), telegram=False)
        db.commit()
        assert n1 is not None
        assert n2 is None  # анти-спам сработал
    finally:
        db.close()


# ---------- Handoff создаёт уведомление ----------

def test_handoff_creates_notification():
    token = _signup("handoff@example.com")
    db = SessionLocal()
    try:
        shop = db.query(models.Shop).filter_by(email="handoff@example.com").first()
        cust = models.Customer(shop_id=shop.id, channel="whatsapp", external_id="7700", name="Ира")
        db.add(cust); db.flush()
        conv = models.Conversation(shop_id=shop.id, customer_id=cust.id, status="active", variables={})
        db.add(conv); db.flush()
        db.add(models.Message(conversation_id=conv.id, role="user", text="позовите менеджера"))
        db.flush()
        notifications.notify_handoff(db, shop, conv)
        db.commit()
    finally:
        db.close()
    items = client.get("/api/notifications", headers=_h(token)).json()["items"]
    assert any(i["type"] == "handoff" for i in items)


# ---------- Мониторинг: важные даты ----------

def test_reminders_match_today_and_tomorrow():
    _signup("rem@example.com")
    db = SessionLocal()
    try:
        shop = db.query(models.Shop).filter_by(email="rem@example.com").first()
        today = datetime.now(UTC).date()
        tomorrow = today + timedelta(days=1)
        far = today + timedelta(days=10)
        bday = f"1990-{today.month:02d}-{today.day:02d}"
        anniv = f"1985-{tomorrow.month:02d}-{tomorrow.day:02d}"
        other = f"2000-{far.month:02d}-{far.day:02d}"
        cust = models.Customer(
            shop_id=shop.id, channel="whatsapp", external_id="7701", name="Олег",
            important_dates=[
                {"label": "День рождения", "date": bday, "recurring": True},
                {"label": "Годовщина", "date": anniv, "recurring": True},
                {"label": "Прочее", "date": other, "recurring": True},
            ],
        )
        db.add(cust); db.commit()
        sent = monitoring.check_reminders_for_shop(db, shop)
        db.commit()
        assert sent >= 2
    finally:
        db.close()


# ---------- Мониторинг: ежедневная сводка ----------

def test_daily_summary_build_and_force():
    _signup("sum@example.com")
    db = SessionLocal()
    try:
        shop = db.query(models.Shop).filter_by(email="sum@example.com").first()
        shop.tg_bot_token = "x"; shop.tg_chat_id = "1"
        cust = models.Customer(shop_id=shop.id, channel="whatsapp", external_id="7702")
        db.add(cust); db.flush()
        now = datetime.now(UTC)
        db.add(models.Order(shop_id=shop.id, customer_id=cust.id, status="paid",
                            total=5000, items=[], details={}, created_at=now))
        db.add(models.Conversation(shop_id=shop.id, customer_id=cust.id, status="active",
                                   variables={}, created_at=now))
        db.commit()
        s = monitoring.build_daily_summary(db, shop, datetime.now(monitoring._shop_tz(shop)))
        assert s["paid"] == 1 and s["revenue"] == 5000.0
        # force=True игнорирует час и создаёт запись
        assert monitoring.send_daily_summary_for_shop(db, shop, force=True) is True
        db.commit()
    finally:
        db.close()


# ---------- Мониторинг: дожим брошенных диалогов ----------

def test_followup_abandoned_dialog():
    _signup("fu@example.com")
    db = SessionLocal()
    try:
        shop = db.query(models.Shop).filter_by(email="fu@example.com").first()
        cust = models.Customer(shop_id=shop.id, channel="sim", external_id="7703", name="Аня")
        db.add(cust); db.flush()
        old = datetime.now(UTC) - timedelta(hours=30)
        conv = models.Conversation(shop_id=shop.id, customer_id=cust.id, status="active", variables={})
        db.add(conv); db.flush()
        db.add(models.Message(conversation_id=conv.id, role="user", text="привет", created_at=old))
        db.add(models.Message(conversation_id=conv.id, role="bot", text="здравствуйте", created_at=old))
        db.commit()
        nudged = monitoring.followup_abandoned_for_shop(db, shop)
        db.commit()
        assert nudged == 1
        # Повторный прогон не дожимает снова.
        assert monitoring.followup_abandoned_for_shop(db, shop) == 0
    finally:
        db.close()
