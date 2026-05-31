from app.ai import _heuristic_intent


def test_question_with_qmark():
    r = _heuristic_intent("а есть другие цветы?")
    assert r["intent"] in {"question", "switch_catalog"}


def test_switch_catalog_keyword():
    r = _heuristic_intent("покажи каталог")
    assert r["intent"] == "switch_catalog"


def test_handoff_keyword():
    r = _heuristic_intent("позовите оператора")
    assert r["intent"] == "handoff"


def test_plain_answer():
    r = _heuristic_intent("на день рождения маме")
    assert r["intent"] == "answer"
    assert r["value"] == "на день рождения маме"


def test_a_prefix_question():
    r = _heuristic_intent("а сколько стоит доставка")
    assert r["intent"] == "question"
