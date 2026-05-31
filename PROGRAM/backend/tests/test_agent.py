"""Тесты LLM-агента с моком LLM-вызова."""
from app import agent, models
from app.database import Base, SessionLocal, engine


def _setup(db, graph=None):
    shop = models.Shop(email="a@a.a", password_hash="x", name="Flora", currency="RUB")
    db.add(shop); db.flush()
    db.add(models.Product(shop_id=shop.id, name="Букет Нежность",
                          description="25 белых роз", price=4500))
    graph = graph or {
        "nodes": [
            {"id": "s", "data": {"kind": "start"}},
            {"id": "a", "data": {"kind": "agent"}},
            {"id": "e", "data": {"kind": "end"}},
        ],
        "edges": [
            {"source": "s", "target": "a"},
            {"source": "a", "target": "e"},
        ],
    }
    flow = models.Flow(shop_id=shop.id, name="A", graph=graph, is_active=True)
    db.add(flow); db.flush()
    cust = models.Customer(shop_id=shop.id, channel="sim", external_id="u1", name="U")
    db.add(cust); db.flush()
    conv = models.Conversation(shop_id=shop.id, customer_id=cust.id, flow_id=flow.id,
                               variables={}, status="active")
    db.add(conv); db.flush()
    return shop, conv


def _last_bot(conv):
    for m in reversed(conv.messages):
        if m.role == "bot":
            return m.text
    return ""


def test_agent_save_slot_via_tool(monkeypatch):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        shop, conv = _setup(db)

        def fake_llm(shop, system, history, user_text):
            return {
                "reply": "Отлично, записал номер. Укажите адрес?",
                "actions": [{"type": "save_slot", "name": "phone", "value": "+79991234567"}],
            }
        monkeypatch.setattr(agent, "_call_llm", fake_llm)

        agent.run_agent_turn(db, shop, conv, "Мой номер 89991234567")
        db.flush()
        assert conv.variables.get("phone") == "+79991234567"
        assert "адрес" in _last_bot(conv).lower()
    finally:
        db.close()


def test_agent_show_catalog(monkeypatch):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        shop, conv = _setup(db)

        monkeypatch.setattr(agent, "_call_llm", lambda *a, **kw: {
            "reply": "Вот что у нас есть:",
            "actions": [{"type": "show_catalog"}],
        })
        agent.run_agent_turn(db, shop, conv, "а другие цветы есть?")
        db.flush()
        texts = [m.text for m in conv.messages if m.role == "bot"]
        assert any("Букет Нежность" in t for t in texts)
    finally:
        db.close()


def test_agent_handoff(monkeypatch):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        shop, conv = _setup(db)
        monkeypatch.setattr(agent, "_call_llm", lambda *a, **kw: {
            "reply": "Минутку, передам менеджеру.",
            "actions": [{"type": "handoff"}],
        })
        agent.run_agent_turn(db, shop, conv, "позовите живого")
        db.flush()
        assert conv.status == "handoff"
    finally:
        db.close()


def test_agent_invoice(monkeypatch):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        shop, conv = _setup(db)
        conv.variables = {
            "recipient": "девушка", "occasion": "ДР",
            "chosen_product": "Букет Нежность",
            "name": "Иван", "phone": "+79991234567",
            "address": "Москва, Тверская 1", "delivery_date": "2025-06-15",
        }
        db.flush()

        monkeypatch.setattr(agent, "_call_llm", lambda *a, **kw: {
            "reply": "Оформляю счёт.",
            "actions": [{"type": "create_invoice"}],
        })
        agent.run_agent_turn(db, shop, conv, "да, всё верно")
        db.flush()
        assert conv.status == "pending_payment"
        order = db.query(models.Order).filter_by(shop_id=shop.id).first()
        assert order is not None
        assert order.total > 0
    finally:
        db.close()


def test_agent_fallback_when_llm_returns_none(monkeypatch):
    """Если LLM недоступен, агент всё равно что-то говорит (не падает)."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        shop, conv = _setup(db)
        monkeypatch.setattr(agent, "_call_llm", lambda *a, **kw: None)
        agent.run_agent_turn(db, shop, conv, None)
        db.flush()
        last = _last_bot(conv)
        assert last  # что-то отправили
        assert "Flora" in last or "букет" in last.lower()
    finally:
        db.close()


def test_pre_extract_multi_no_reask_when_llm_down(monkeypatch):
    """Клиент в одном сообщении даёт имя+телефон+адрес+дату, LLM недоступен.

    Бот должен сохранить ВСЁ детерминированно и задать ровно один следующий
    вопрос (про недостающий слот), а не переспрашивать уже данное.
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        shop, conv = _setup(db)
        # уже выбрали получателя/повод/букет — осталось контактное
        conv.variables = {"recipient": "жене", "occasion": "годовщина",
                          "chosen_product": "Букет Нежность"}
        db.flush()
        monkeypatch.setattr(agent, "_call_llm", lambda *a, **kw: None)
        agent.run_agent_turn(
            db, shop, conv,
            "Меня зовут Иван, телефон +77001234567, привезти на ул Абая 10 кв 5 завтра вечером",
        )
        db.flush()
        v = conv.variables
        assert v.get("name") == "Иван"
        assert v.get("phone") == "+77001234567"
        assert v.get("address")
        assert v.get("delivery_date")
        # всё собрано → бот должен перейти к оформлению, без переспросов
        last = _last_bot(conv).lower()
        assert "имя" not in last and "телефон" not in last and "адрес" not in last
    finally:
        db.close()


def test_pre_extract_runs_before_llm_and_fills_vars(monkeypatch):
    """Pre-extract срабатывает ДО LLM: телефон уже в variables к моменту вызова."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        shop, conv = _setup(db)
        conv.variables = {"recipient": "жене", "occasion": "годовщина",
                          "chosen_product": "Букет Нежность", "name": "Иван",
                          "address": "ул Абая 10", "delivery_date": "2025-06-15"}
        db.flush()
        seen = {}

        def fake_llm(shop, system, history, user_text):
            seen["system"] = system
            return {"reply": "Готово, оформляю!", "actions": []}
        monkeypatch.setattr(agent, "_call_llm", fake_llm)
        agent.run_agent_turn(db, shop, conv, "мой номер +7 700 123 45 67")
        db.flush()
        assert conv.variables.get("phone") == "+77001234567"
        # LLM увидел телефон в собранных данных (не должен переспрашивать)
        assert "+77001234567" in seen["system"]
    finally:
        db.close()


def test_pre_extract_does_not_grab_quantity_as_address(monkeypatch):
    """«хочу 3 розы» не должно попасть в адрес (нет уличного маркера)."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        shop, conv = _setup(db)
        vars_ = {}
        saved = agent._pre_extract("хочу 3 розы", ["address", "phone"], vars_)
        assert "address" not in saved
        assert not vars_.get("address")
    finally:
        db.close()


def test_gemini_quota_error_detection():
    err = Exception("429 You exceeded your current quota ... RESOURCE_EXHAUSTED")
    assert agent._is_quota_error(err) is True
    assert agent._is_quota_error(ValueError("bad json")) is False


def test_name_phrase_handles_zovut_with_space():
    """Регресс: «меня зовут Иван» раньше не парсилось (группа не съедала пробел)."""
    assert agent._extract_name_phrase("меня зовут Иван") == "Иван"
    assert agent._extract_name_phrase("Здравствуйте, меня зовут Анна Петрова") in ("Анна", "Анна Петрова")
    # «для жены» не должно дать имя (хвост слова на «я» больше не ловится)
    assert agent._extract_name_phrase("букет для жены на годовщину") is None


def test_keyword_phrase_extracts_short_recipient():
    val = agent._keyword_phrase("Хочу букет для жены на годовщину", "хочу букет для жены на годовщину", agent._RECIPIENT_KEYWORDS)
    assert val == "жены"
