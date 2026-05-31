"""Сидирование демо-флоу и товаров для нового магазина."""
import copy

from sqlalchemy.orm import Session

from . import models

# Современный AI-agent флоу (один узел делает всё: сбор данных, каталог, инвойс).
AGENT_GRAPH = {
    "nodes": [
        {"id": "start", "type": "default", "position": {"x": 40, "y": 40},
         "data": {"kind": "start", "label": "Старт"}},
        {"id": "agent", "type": "default", "position": {"x": 40, "y": 160},
         "data": {
             "kind": "agent",
             "label": "AI-агент",
             "required_slots": [
                 "recipient", "occasion", "chosen_product",
                 "name", "phone", "address", "delivery_date",
             ],
             "delivery_fee": 500,
         }},
        {"id": "end", "type": "default", "position": {"x": 40, "y": 300},
         "data": {"kind": "end", "label": "Завершить",
                  "text": "Спасибо! После оплаты курьер подтвердит доставку. 🌷"}},
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "agent"},
        {"id": "e2", "source": "agent", "target": "end"},
    ],
}


# Старый скриптованный флоу — оставлен для обратной совместимости.
LEGACY_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "default", "position": {"x": 40, "y": 40},
         "data": {"kind": "start", "label": "Старт"}},
        {"id": "n2", "type": "default", "position": {"x": 40, "y": 140},
         "data": {"kind": "message", "label": "Приветствие",
                  "text": "Здравствуйте! 🌸 Это {shop} — цветы с доставкой. Помогу подобрать букет. Для кого и по какому поводу?"}},
        {"id": "n3", "type": "default", "position": {"x": 40, "y": 260},
         "data": {"kind": "collect", "label": "Повод",
                  "question": "Расскажите, для кого и по какому поводу?",
                  "variable": "occasion",
                  "extract_prompt": "Извлеки повод и получателя одной фразой"}},
        {"id": "n4", "type": "default", "position": {"x": 40, "y": 400},
         "data": {"kind": "catalog", "label": "Каталог"}},
        {"id": "n5", "type": "default", "position": {"x": 40, "y": 520},
         "data": {"kind": "collect", "label": "Имя", "question": "Как к вам обращаться?", "variable": "name"}},
        {"id": "n6", "type": "default", "position": {"x": 40, "y": 640},
         "data": {"kind": "collect", "label": "Телефон",
                  "question": "Оставьте номер телефона для связи.", "variable": "phone",
                  "extract_prompt": "Извлеки номер телефона"}},
        {"id": "n7", "type": "default", "position": {"x": 40, "y": 760},
         "data": {"kind": "collect", "label": "Адрес",
                  "question": "Адрес доставки (город, улица, дом).", "variable": "address"}},
        {"id": "n8", "type": "default", "position": {"x": 40, "y": 880},
         "data": {"kind": "collect", "label": "Дата",
                  "question": "Дата и время доставки?", "variable": "delivery_date"}},
        {"id": "n9", "type": "default", "position": {"x": 40, "y": 1000},
         "data": {"kind": "order_summary", "label": "Сводка"}},
        {"id": "n10", "type": "default", "position": {"x": 40, "y": 1100},
         "data": {"kind": "invoice", "label": "Счёт", "delivery_fee": 500}},
        {"id": "n11", "type": "default", "position": {"x": 40, "y": 1220},
         "data": {"kind": "end", "label": "Завершить",
                  "text": "Спасибо! После оплаты курьер подтвердит доставку. 🌷"}},
    ],
    "edges": [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3"},
        {"id": "e3", "source": "n3", "target": "n4"},
        {"id": "e4", "source": "n4", "target": "n5"},
        {"id": "e5", "source": "n5", "target": "n6"},
        {"id": "e6", "source": "n6", "target": "n7"},
        {"id": "e7", "source": "n7", "target": "n8"},
        {"id": "e8", "source": "n8", "target": "n9"},
        {"id": "e9", "source": "n9", "target": "n10"},
        {"id": "e10", "source": "n10", "target": "n11"},
    ],
}

DEMO_PRODUCTS = [
    {"name": "Букет «Нежность»", "category": "Букеты", "description": "25 белых и розовых роз", "price": 4500, "available_today": True},
    {"name": "Букет «Весна»", "category": "Букеты", "description": "Тюльпаны 51 шт, микс", "price": 3900, "available_today": True},
    {"name": "Букет «Страсть»", "category": "Розы", "description": "25 красных роз премиум", "price": 5200, "available_today": True},
    {"name": "Букет «Полевой»", "category": "Букеты", "description": "Ромашки, хризантемы, зелень", "price": 2800, "available_today": False},
]


def build_agent_flow(shop_name: str) -> dict:
    return copy.deepcopy(AGENT_GRAPH)


def seed_shop_defaults(db: Session, shop: models.Shop):
    """Вызывается при регистрации нового магазина."""
    db.add(models.Flow(
        shop_id=shop.id,
        name="AI-агент (рекомендовано)",
        description="Один агентский узел ведёт весь диалог и создаёт счёт.",
        is_active=True,
        graph=build_agent_flow(shop.name),
    ))
    for p in DEMO_PRODUCTS:
        db.add(models.Product(shop_id=shop.id, is_active=True, **p))
    db.flush()
