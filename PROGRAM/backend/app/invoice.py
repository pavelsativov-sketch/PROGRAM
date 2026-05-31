from __future__ import annotations

from sqlalchemy.orm import Session

from . import models
from .config import settings


def create_invoice_for_conversation(db: Session, shop: models.Shop, conv: models.Conversation, node_data: dict) -> models.Order:
    v = dict(conv.variables or {})
    items, total = [], 0.0

    product_name = v.get("chosen_product") or v.get("bouquet") or node_data.get("default_product")
    if product_name:
        prod = db.query(models.Product).filter(
            models.Product.shop_id == shop.id,
            models.Product.name.ilike(f"%{product_name}%"),
            models.Product.is_active == True,
        ).first()
        if prod:
            qty = int(v.get("quantity") or 1)
            items.append({"name": prod.name, "qty": qty, "price": prod.price})
            total = prod.price * qty
        else:
            price = float(node_data.get("fallback_price") or 2500)
            items.append({"name": product_name, "qty": 1, "price": price})
            total = price
    if not items:
        price = float(node_data.get("fallback_price") or 2500)
        items.append({"name": "Букет на ваш выбор", "qty": 1, "price": price})
        total = price

    delivery = float(node_data.get("delivery_fee") or 0)
    if delivery:
        items.append({"name": "Доставка", "qty": 1, "price": delivery})
        total += delivery

    order = models.Order(
        shop_id=shop.id,
        conversation_id=conv.id,
        customer_id=conv.customer_id,
        items=items,
        total=total,
        status="pending_payment",
        details={
            "name": v.get("name"),
            "phone": v.get("phone"),
            "address": v.get("address"),
            "delivery_date": v.get("delivery_date"),
            "wishes": v.get("wishes"),
        },
    )
    db.add(order)
    db.flush()
    token = settings.sign_pay_token(order.id, shop.id)
    order.payment_link = f"{settings.public_base_url}/pay/{order.id}?t={token}"
    db.flush()
    # Уведомление магазина в Telegram о новом счёте — best-effort, ошибки глушим.
    try:
        from . import notifier
        notifier.notify_new_order(shop, order)
    except Exception:
        pass
    return order
