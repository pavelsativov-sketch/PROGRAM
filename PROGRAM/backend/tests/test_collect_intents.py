"""
Проверяем, что collect-узел НЕ записывает вопросы/запросы каталога в переменную.
Эмулируем LLM через monkeypatch на ai_classify_intent.
"""
from app import flow_engine, models
from app.database import Base, SessionLocal, engine


def _setup_conv(db):
    shop = models.Shop(email="t@t.t", password_hash="x", name="Flora")
    db.add(shop); db.flush()
    db.add(models.Product(shop_id=shop.id, name="Розы", description="25 роз", price=4500))
    graph = {
        "nodes": [
            {"id": "s", "data": {"kind": "start"}},
            {"id": "q", "data": {"kind": "collect", "question": "Повод?", "variable": "occasion"}},
            {"id": "e", "data": {"kind": "end"}},
        ],
        "edges": [
            {"source": "s", "target": "q"},
            {"source": "q", "target": "e"},
        ],
    }
    flow = models.Flow(shop_id=shop.id, name="T", graph=graph, is_active=True)
    db.add(flow); db.flush()
    customer = models.Customer(shop_id=shop.id, channel="sim", external_id="u1", name="U")
    db.add(customer); db.flush()
    conv = models.Conversation(shop_id=shop.id, customer_id=customer.id, flow_id=flow.id,
                               variables={}, status="active")
    db.add(conv); db.flush()
    return shop, conv


def _ensure_tables():
    Base.metadata.create_all(bind=engine)


def test_collect_question_does_not_store(monkeypatch):
    _ensure_tables()
    db = SessionLocal()
    try:
        shop, conv = _setup_conv(db)
        flow_engine.run_conversation(db, shop, conv, None)  # эмитим вопрос
        db.flush()
        assert conv.variables == {}

        # клиент задаёт встречный вопрос
        monkeypatch.setattr(flow_engine, "ai_classify_intent",
                            lambda *a, **kw: {"intent": "question", "value": "",
                                              "reply": "Да, есть и другие букеты.", "valid": False})
        flow_engine.run_conversation(db, shop, conv, "а есть другие цветы?")
        db.flush()
        # Переменная НЕ должна быть записана
        assert conv.variables.get("occasion") in (None, "")
        # И мы остались на том же узле
        assert conv.current_node_id == "q"
    finally:
        db.close()


def test_collect_switch_catalog_does_not_store(monkeypatch):
    _ensure_tables()
    db = SessionLocal()
    try:
        shop, conv = _setup_conv(db)
        flow_engine.run_conversation(db, shop, conv, None)
        monkeypatch.setattr(flow_engine, "ai_classify_intent",
                            lambda *a, **kw: {"intent": "switch_catalog", "value": "",
                                              "reply": "", "valid": False})
        flow_engine.run_conversation(db, shop, conv, "покажи каталог")
        db.flush()
        assert conv.variables.get("occasion") in (None, "")
        assert conv.current_node_id == "q"
    finally:
        db.close()


def test_collect_handoff(monkeypatch):
    _ensure_tables()
    db = SessionLocal()
    try:
        shop, conv = _setup_conv(db)
        flow_engine.run_conversation(db, shop, conv, None)
        # глобальный детектор поймает "оператор"
        flow_engine.run_conversation(db, shop, conv, "позовите оператора, пожалуйста")
        db.flush()
        assert conv.status == "handoff"
    finally:
        db.close()


def test_collect_answer_stores_and_advances(monkeypatch):
    _ensure_tables()
    db = SessionLocal()
    try:
        shop, conv = _setup_conv(db)
        flow_engine.run_conversation(db, shop, conv, None)
        monkeypatch.setattr(flow_engine, "ai_classify_intent",
                            lambda *a, **kw: {"intent": "answer", "value": "День рождения",
                                              "reply": "", "valid": True})
        flow_engine.run_conversation(db, shop, conv, "На день рождения маме")
        db.flush()
        assert conv.variables.get("occasion") == "День рождения"
        # advanced past collect → next is "end", закрылось
        assert conv.status == "closed"
    finally:
        db.close()


def test_collect_invalid_phone_reasks():
    _ensure_tables()
    db = SessionLocal()
    try:
        shop = models.Shop(email="p@p.p", password_hash="x", name="P")
        db.add(shop); db.flush()
        graph = {
            "nodes": [
                {"id": "s", "data": {"kind": "start"}},
                {"id": "q", "data": {"kind": "collect", "question": "Телефон?", "variable": "phone"}},
                {"id": "e", "data": {"kind": "end"}},
            ],
            "edges": [
                {"source": "s", "target": "q"},
                {"source": "q", "target": "e"},
            ],
        }
        flow = models.Flow(shop_id=shop.id, name="T", graph=graph, is_active=True)
        db.add(flow); db.flush()
        c = models.Customer(shop_id=shop.id, channel="sim", external_id="u2", name="")
        db.add(c); db.flush()
        conv = models.Conversation(shop_id=shop.id, customer_id=c.id, flow_id=flow.id,
                                   variables={}, status="active")
        db.add(conv); db.flush()
        flow_engine.run_conversation(db, shop, conv, None)
        # без AI — эвристика: «привет» не вопрос, intent=answer, value="привет", но validate_variable отклонит
        flow_engine.run_conversation(db, shop, conv, "привет")
        db.flush()
        assert conv.variables.get("phone") in (None, "")
        assert conv.current_node_id == "q"
    finally:
        db.close()
