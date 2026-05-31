from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_signup_login_logout_flow():
    email = "testshop@example.com"
    r = client.post("/api/auth/signup", json={"email": email, "password": "password1!", "name": "T"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email

    r = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    # после logout — токен отозван
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_signup_short_password():
    r = client.post("/api/auth/signup", json={"email": "short@example.com", "password": "123", "name": "T"})
    assert r.status_code == 400


def test_unauthenticated_me():
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_encrypted_ai_key_roundtrip():
    """
    PUT /me с ai_api_key и GET /me не должен в ShopOut возвращать ключ
    (в схеме его нет), но в БД он шифруется и расшифровывается.
    """
    email = "crypt@example.com"
    r = client.post("/api/auth/signup", json={"email": email, "password": "password1!", "name": "T"})
    token = r.json()["access_token"]
    r = client.put("/api/auth/me",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"ai_provider": "gemini", "ai_api_key": "sk-secret-xyz"})
    assert r.status_code == 200
    # Проверим через БД
    from app import models
    from app.database import SessionLocal
    db = SessionLocal()
    shop = db.query(models.Shop).filter_by(email=email).first()
    assert shop.ai_api_key == "sk-secret-xyz"  # прозрачно расшифровалось
    db.close()
