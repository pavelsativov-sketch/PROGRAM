from app.variables import validate_variable


def test_phone_ok():
    ok, v, _ = validate_variable("phone", "+7 (999) 123-45-67")
    assert ok and v.startswith("+")


def test_phone_normalize_8():
    ok, v, _ = validate_variable("phone", "89991234567")
    assert ok and v == "+79991234567"


def test_phone_rejects_garbage():
    ok, v, hint = validate_variable("phone", "привет")
    assert not ok and "номер" in hint.lower()


def test_email_ok():
    ok, v, _ = validate_variable("email", "a@b.co")
    assert ok


def test_email_rejects():
    ok, _, _ = validate_variable("email", "not-email")
    assert not ok


def test_date_parses_iso():
    ok, v, _ = validate_variable("delivery_date", "2025-06-15")
    assert ok and v == "2025-06-15"


def test_date_parses_tomorrow():
    ok, v, _ = validate_variable("delivery_date", "завтра")
    assert ok and len(v) == 10


def test_name_ok():
    ok, v, _ = validate_variable("name", "Анна")
    assert ok and v == "Анна"


def test_name_rejects_single_char():
    ok, _, _ = validate_variable("name", "A")
    assert not ok


def test_unknown_variable_passes_nonempty():
    ok, v, _ = validate_variable("occasion", "день рождения")
    assert ok and v == "день рождения"


def test_empty_rejected():
    ok, _, _ = validate_variable("occasion", "")
    assert not ok
