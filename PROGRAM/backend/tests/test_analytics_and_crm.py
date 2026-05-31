"""
Тесты на новые роутеры:
- /api/analytics/summary — KPI «Сегодня», воронка, тренд недели
- /api/customers — CRM list + detail + tags/notes
"""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app

client = TestClient(app)


def _signup(email="crm-shop@example.com", name="CRM Shop"):
    r = client.post("/api/auth/signup", json={"email": email, "password": "password1!", "name": name})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_data(shop_email: str):
    """Заносим клиента + два заказа: один сегодня (paid), один неделю назад (paid)."""
    db = SessionLocal()
    try:
        shop = db.query(models.Shop).filter_by(email=shop_email).first()
        cust = models.Customer(
            shop_id=shop.id, channel="whatsapp", external_id="79990000001",
            name="Алина Цвет",
        )
        db.add(cust); db.flush()

        now = datetime.now(timezone.utc)
        today_order = models.Order(
            shop_id=shop.id, customer_id=cust.id, status="paid", total=4500,
            items=[{"name": "Букет «Нежность»", "qty": 1, "price": 4500}],
            details={"name": "Алина", "phone": "+7", "delivery_date": "сегодня"},
            created_at=now,
        )
        old_order = models.Order(
            shop_id=shop.id, customer_id=cust.id, status="delivered", total=3000,
            items=[{"name": "Букет «Весна»", "qty": 1, "price": 3000}],
            details={"name": "Алина"},
            created_at=now - timedelta(days=8),  # прошлая неделя — для тренда
        )
        db.add_all([today_order, old_order])
        # Диалог в handoff — должен попасть в conversations.handoff
        conv = models.Conversation(
            shop_id=shop.id, customer_id=cust.id, status="handoff", variables={},
        )
        db.add(conv)
        db.commit()
        return cust.id
    finally:
        db.close()


# ---------- Analytics ----------

def test_analytics_summary_unauth():
    r = client.get("/api/analytics/summary")
    assert r.status_code == 401


def test_analytics_summary_basic():
    token = _signup("an1@example.com")
    cust_id = _seed_data("an1@example.com")  # noqa: F841

    r = client.get("/api/analytics/summary", headers=_h(token))
    assert r.status_code == 200, r.text
    data = r.json()

    # Сегодня — 1 заказ оплачен на 4500
    assert data["today"]["orders"] == 1
    assert data["today"]["paid_orders"] == 1
    assert data["today"]["revenue"] == 4500.0
    # Неделя — только сегодняшний (прошлый > 7 дней)
    assert data["week"]["revenue"] == 4500.0
    # Воронка: paid + delivered
    assert data["pipeline"].get("paid") == 1
    assert data["pipeline"].get("delivered") == 1
    # Канал whatsapp по этому клиенту — 2 заказа
    assert data["by_channel"].get("whatsapp") == 2
    # Handoff в диалогах — 1
    assert data["conversations"]["handoff"] == 1
    # Топ-продукт за месяц — Букет «Нежность» первый
    assert data["top_products"][0]["name"] == "Букет «Нежность»"
    assert data["currency"]  # любая валюта магазина


def test_analytics_isolated_per_shop():
    """Магазин A не должен видеть KPI магазина B."""
    token_a = _signup("a@example.com", name="A")
    token_b = _signup("b@example.com", name="B")
    _seed_data("a@example.com")

    a = client.get("/api/analytics/summary", headers=_h(token_a)).json()
    b = client.get("/api/analytics/summary", headers=_h(token_b)).json()
    assert a["today"]["orders"] == 1
    assert b["today"]["orders"] == 0
    assert b["pipeline"] == {}


# ---------- Customers ----------

def test_customers_list_and_detail():
    token = _signup("cust1@example.com")
    cust_id = _seed_data("cust1@example.com")

    # список
    r = client.get("/api/customers", headers=_h(token))
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    c = items[0]
    assert c["id"] == cust_id
    assert c["orders"] == 2
    assert c["ltv"] == 7500.0  # 4500 + 3000
    assert c["channel"] == "whatsapp"
    assert c["last_order_at"]  # ISO

    # детальная карточка
    r = client.get(f"/api/customers/{cust_id}", headers=_h(token))
    assert r.status_code == 200
    d = r.json()
    assert d["stats"]["paid_orders"] == 2
    assert d["stats"]["ltv"] == 7500.0
    assert len(d["orders"]) == 2
    assert len(d["conversations"]) == 1


def test_customers_tags_and_notes_normalize():
    token = _signup("cust2@example.com")
    cust_id = _seed_data("cust2@example.com")

    # дубликаты, пробелы, регистр — всё нормализуется
    r = client.put(
        f"/api/customers/{cust_id}", headers=_h(token),
        json={"tags": ["VIP", " vip ", "Корпоратив", ""], "notes": "любит белые пионы"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tags"] == ["VIP", "Корпоратив"]
    assert body["notes"] == "любит белые пионы"

    # детальная карточка тоже отдаёт обновлённое
    d = client.get(f"/api/customers/{cust_id}", headers=_h(token)).json()
    assert d["tags"] == ["VIP", "Корпоратив"]
    assert d["notes"] == "любит белые пионы"


def test_customers_isolation():
    token_a = _signup("ax@example.com")
    token_b = _signup("bx@example.com")
    cust_id = _seed_data("ax@example.com")

    # B не видит клиента A
    r = client.get(f"/api/customers/{cust_id}", headers=_h(token_b))
    assert r.status_code == 404

    # B не может править клиента A
    r = client.put(f"/api/customers/{cust_id}", headers=_h(token_b), json={"tags": ["hack"]})
    assert r.status_code == 404
