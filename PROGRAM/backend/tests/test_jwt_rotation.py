"""Тесты ротации JWT: при login предыдущие токены этого магазина становятся невалидны."""
import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_rotates_previous_tokens():
    email = "rotate@example.com"
    pw = "password1!"
    r = client.post("/api/auth/signup", json={"email": email, "password": pw, "name": "T"})
    assert r.status_code == 200, r.text
    token1 = r.json()["access_token"]

    # token1 валиден.
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
    assert r.status_code == 200

    # Ждём заметно больше tolerance (2 сек в current_shop), чтобы ротация сработала однозначно.
    time.sleep(3.5)

    # Логинимся ещё раз — tokens_valid_after сдвигается.
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    token2 = r.json()["access_token"]
    assert token2 != token1

    # token2 — валиден, token1 — отозван по ротации.
    r2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})
    assert r2.status_code == 200
    r1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
    assert r1.status_code == 401, "Старый токен должен быть невалиден после ротации"
