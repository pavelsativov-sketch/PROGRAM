"""Тесты на улучшенные AI-эвристики:
- мультислотный парсер (имя+телефон+адрес+дата в одном сообщении)
- fuzzy-резолв chosen_product («первый», «#2», подстрока, тайтл по словам)
- анти-мусор: «не знаю», «посоветуй» НЕ должны попадать в slot
- humanize_variable: ISO-дата → «25 декабря»

Тесты не используют LLM — только pure-python функции, поэтому стабильны и быстрые.
"""
from datetime import date, datetime, timedelta

import pytest

from app import models
# Импорт app.main триггерит Base.metadata.create_all() для sqlite в тестах.
from app.main import app  # noqa: F401  (import for side effect: schema bootstrap)
from app.agent import (
    DEFAULT_REQUIRED_SLOTS,
    _find_product,
    _heuristic_save_multi,
    _heuristic_save_slot,
)
from app.database import SessionLocal
from app.variables import _parse_date, humanize_variable, is_non_answer, validate_variable


# ---------- variables.validate_variable ----------

def test_phone_normalization_8_to_plus7():
    ok, norm, _ = validate_variable("phone", "8 999 555 12 34")
    assert ok and norm == "+79995551234"


def test_phone_with_brackets():
    ok, norm, _ = validate_variable("phone", "+7 (999) 123-45-67")
    assert ok and norm == "+79991234567"


def test_phone_too_short_rejected():
    ok, _, hint = validate_variable("phone", "123")
    assert not ok and hint


def test_name_strips_intro():
    ok, norm, _ = validate_variable("name", "меня зовут анна")
    assert ok and norm == "Анна"


def test_name_titlecase_two_words():
    ok, norm, _ = validate_variable("name", "анна петрова")
    assert ok and norm == "Анна Петрова"


def test_address_self_pickup():
    ok, norm, _ = validate_variable("address", "самовывоз, заберу сам")
    assert ok and norm == "Самовывоз"


def test_address_too_short_rejected():
    ok, _, hint = validate_variable("address", "ул")
    assert not ok and hint


# ---------- variables.parse_date / humanize ----------

def test_date_today_tomorrow():
    today = datetime.now().date()
    assert _parse_date("сегодня") == today.strftime("%Y-%m-%d")
    assert _parse_date("завтра") == (today + timedelta(days=1)).strftime("%Y-%m-%d")
    assert _parse_date("послезавтра") == (today + timedelta(days=2)).strftime("%Y-%m-%d")


def test_date_text_form_ru():
    """«25 декабря» должна распознаваться, причём с вводом года в будущем при необходимости."""
    today = datetime.now().date()
    iso = _parse_date("25 декабря")
    assert iso  # распознали
    parsed = datetime.strptime(iso, "%Y-%m-%d").date()
    assert parsed.month == 12 and parsed.day == 25
    assert parsed >= today  # нет назад в прошлое


def test_date_weekday_in_future():
    today = datetime.now().date()
    iso = _parse_date("в пятницу")
    assert iso
    parsed = datetime.strptime(iso, "%Y-%m-%d").date()
    assert parsed.weekday() == 4
    assert (parsed - today).days >= 1  # будущая пятница


def test_date_iso_format():
    assert _parse_date("2026-01-15") == "2026-01-15"


def test_humanize_date_tomorrow():
    tomorrow = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    s = humanize_variable("delivery_date", tomorrow)
    assert "завтра" in s


def test_humanize_passthrough_other_slot():
    assert humanize_variable("name", "Анна") == "Анна"


# ---------- non-answer detection ----------

@pytest.mark.parametrize("phrase", [
    "не знаю", "хз", "посоветуйте", "на ваш вкус",
    "выбирай ты", "затрудняюсь", "пока не знаю",
])
def test_is_non_answer_positive(phrase):
    assert is_non_answer(phrase)


@pytest.mark.parametrize("phrase", [
    "Анна", "+7 999 555 12 34", "ул Ленина 5", "первый букет",
])
def test_is_non_answer_negative(phrase):
    assert not is_non_answer(phrase)


# ---------- мульти-слотный парсер ----------

def test_multi_extracts_phone_and_name():
    vars_ = {}
    saved = _heuristic_save_multi(
        "Меня зовут Алексей, тел +7 999 555 12 34",
        ["recipient", "occasion", "name", "phone", "address", "delivery_date"],
        vars_,
    )
    assert "name" in saved
    assert "phone" in saved
    assert vars_["name"] == "Алексей"
    assert vars_["phone"] == "+79995551234"


def test_multi_extracts_full_dossier():
    vars_ = {}
    text = "Анна, +7 (999) 123-45-67, ул Абая 10 кв 5, завтра"
    saved = _heuristic_save_multi(
        text,
        ["name", "phone", "address", "delivery_date"],
        vars_,
    )
    # Минимум телефон + дата + что-то ещё
    assert "phone" in saved
    assert "delivery_date" in saved
    assert vars_["phone"] == "+79991234567"
    # date — корректный ISO, завтрашний день
    expected = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    assert vars_["delivery_date"] == expected


def test_multi_does_not_overwrite_already_collected():
    """Если slot уже не в `missing`, парсер не должен его перезаписать."""
    vars_ = {"name": "Изначальное Имя"}
    saved = _heuristic_save_multi(
        "Меня зовут Алексей",
        ["phone", "address"],  # name НЕ в missing
        vars_,
    )
    assert "name" not in saved
    assert vars_["name"] == "Изначальное Имя"


# ---------- одиночный парсер ----------

def test_heuristic_skips_non_answer():
    """«не знаю» в ответе на recipient НЕ должно попадать в slot."""
    vars_ = {}
    res = _heuristic_save_slot(
        "не знаю", DEFAULT_REQUIRED_SLOTS, vars_,
    )
    assert res is None
    assert "recipient" not in vars_


def test_heuristic_skips_question():
    vars_ = {}
    res = _heuristic_save_slot(
        "А сколько стоит доставка?", DEFAULT_REQUIRED_SLOTS, vars_,
    )
    assert res is None


def test_heuristic_skips_catalog_request():
    vars_ = {}
    res = _heuristic_save_slot(
        "покажите варианты", DEFAULT_REQUIRED_SLOTS, vars_,
    )
    assert res is None


def test_heuristic_finds_phone_anywhere():
    """Телефон ловится даже когда первым в `missing` стоит другой слот."""
    vars_ = {}
    res = _heuristic_save_slot(
        "+7 999 555 12 34",
        ["recipient", "phone", "address"],  # recipient первый, но телефон важнее
        vars_,
    )
    assert res == "phone"
    assert vars_["phone"] == "+79995551234"


# ---------- fuzzy-резолв chosen_product ----------

def _make_shop_with_products(names: list[str]) -> int:
    db = SessionLocal()
    try:
        shop = models.Shop(
            email=f"agent-fuzzy-{datetime.now().timestamp()}@example.com",
            password_hash="x",
            name="FuzzyShop",
        )
        db.add(shop); db.flush()
        for n in names:
            db.add(models.Product(shop_id=shop.id, name=n, price=1000, is_active=True))
        db.commit()
        return shop.id
    finally:
        db.close()


def test_find_product_by_ordinal():
    shop_id = _make_shop_with_products(["Букет «Нежность»", "Букет «Весна»", "Букет «Страсть»"])
    db = SessionLocal()
    try:
        p = _find_product(db, shop_id, "первый")
        assert p and p.name == "Букет «Нежность»"
        p = _find_product(db, shop_id, "второй")
        assert p and p.name == "Букет «Весна»"
        p = _find_product(db, shop_id, "#3")
        assert p and p.name == "Букет «Страсть»"
        p = _find_product(db, shop_id, "3")
        assert p and p.name == "Букет «Страсть»"
    finally:
        db.close()


def test_find_product_by_substring():
    shop_id = _make_shop_with_products(["Букет «Нежность»", "Букет «Весна»"])
    db = SessionLocal()
    try:
        p = _find_product(db, shop_id, "нежность")
        assert p and p.name == "Букет «Нежность»"
        p = _find_product(db, shop_id, "Весна")
        assert p and p.name == "Букет «Весна»"
    finally:
        db.close()


def test_find_product_by_word_overlap():
    """Совпадение по словам, без точного вхождения."""
    shop_id = _make_shop_with_products(["Красные розы премиум", "Тюльпаны микс"])
    db = SessionLocal()
    try:
        p = _find_product(db, shop_id, "красные розы")
        assert p and p.name == "Красные розы премиум"
    finally:
        db.close()


def test_find_product_no_match():
    shop_id = _make_shop_with_products(["Букет «Нежность»"])
    db = SessionLocal()
    try:
        assert _find_product(db, shop_id, "несуществующий букет xyz") is None
        assert _find_product(db, shop_id, "") is None
    finally:
        db.close()
