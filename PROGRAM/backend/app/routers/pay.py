from base64 import b64encode
from html import escape as h

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from qrcode.image.svg import SvgImage
from sqlalchemy.orm import Session

from .. import models
from ..audit import log_action
from ..config import settings
from ..database import get_db
from ..rate_limit import limiter

router = APIRouter(tags=["pay"])


def _verify_or_404(o: models.Order, t: str) -> None:
    if not settings.verify_pay_token(o.id, o.shop_id, t):
        raise HTTPException(404)


def _money(v: float) -> str:
    return f"{v:.0f}"


def _qr_data_url(text: str) -> str:
    qr = qrcode.QRCode(border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(image_factory=SvgImage)
    svg = img.to_string(encoding="unicode")
    return "data:image/svg+xml;base64," + b64encode(svg.encode("utf-8")).decode("ascii")


def _status_label(status: str) -> str:
    return {
        "new": "Новый",
        "pending_payment": "Ожидает оплаты",
        "payment_review": "Проверка оплаты",
        "paid": "Оплачен",
        "delivered": "Доставлен",
        "cancelled": "Отменен",
    }.get(status, status)


@router.get("/pay/{order_id}", response_class=HTMLResponse)
def pay_page(order_id: int, t: str = Query(default=""), db: Session = Depends(get_db)):
    o = db.get(models.Order, order_id)
    if not o:
        raise HTTPException(404)
    _verify_or_404(o, t)
    shop = db.get(models.Shop, o.shop_id)
    currency = h(shop.currency or "")
    items_html = "".join(
        f"<tr><td>{h(i.get('name', ''))}</td>"
        f"<td>{h(str(i.get('qty', 1)))}</td>"
        f"<td>{h(_money(float(i.get('price', 0))))} {currency}</td></tr>"
        for i in (o.items or [])
    )
    details = o.details or {}
    paid = o.status == "paid"
    reviewing = o.status == "payment_review"
    status_class = "paid" if paid else "review" if reviewing else ""
    kaspi_phone = (shop.kaspi_phone or "").strip()
    kaspi_name = (shop.kaspi_name or shop.name or "").strip()
    pay_comment = f"Заказ №{o.id}"

    qr_src = (shop.kaspi_qr_url or "").strip()
    if not qr_src and kaspi_phone:
        qr_src = _qr_data_url(
            f"Kaspi перевод\nПолучатель: {kaspi_name}\nТелефон: {kaspi_phone}\n"
            f"Сумма: {_money(o.total)} {shop.currency}\nКомментарий: {pay_comment}"
        )
    qr_html = (
        f'<img class="qr" src="{h(qr_src)}" alt="Kaspi QR">'
        if qr_src
        else '<div class="qr empty">QR Kaspi пока не настроен</div>'
    )

    instructions = (shop.payment_instructions or "").strip() or (
        "Откройте Kaspi.kz, отсканируйте QR-код или сделайте перевод на номер ниже. "
        "В комментарии к платежу укажите номер заказа."
    )
    button_html = "" if paid or reviewing else (
        f'<form method="post" action="/pay/{o.id}/confirm?t={h(t)}">'
        '<button class="btn" type="submit">Я оплатил через Kaspi</button>'
        "</form>"
    )
    review_html = (
        '<div class="notice">Оплата отправлена на проверку менеджеру. Мы подтвердим заказ после проверки перевода в Kaspi.</div>'
        if reviewing else ""
    )
    paid_html = '<div class="notice paid-note">Оплата подтверждена. Спасибо!</div>' if paid else ""

    return f"""
<!doctype html><html><head><meta charset="utf-8"><title>Счёт №{o.id}</title>
<meta name="referrer" content="no-referrer">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:760px;margin:32px auto;padding:0 16px;color:#1f2937;background:#f7f7fb}}
.page{{background:#fff;border-radius:18px;padding:24px;box-shadow:0 12px 36px rgba(15,23,42,.08)}}h1{{margin:0 0 8px}}
.muted{{color:#6b7280}}table{{width:100%;border-collapse:collapse;margin:16px 0}}td,th{{border-bottom:1px solid #eee;padding:10px;text-align:left}}
.total{{font-size:24px;font-weight:700;margin-top:16px}}.kaspi{{display:grid;grid-template-columns:240px 1fr;gap:20px;align-items:center;margin-top:20px;padding:18px;border:1px solid #fde68a;border-radius:14px;background:#fffbeb}}
.qr{{width:220px;height:220px;object-fit:contain;background:#fff;border-radius:12px;border:1px solid #f3f4f6}}.qr.empty{{display:flex;align-items:center;justify-content:center;text-align:center;padding:18px;color:#92400e}}
.copy{{font-size:22px;font-weight:700;margin:6px 0}}.comment{{font-family:ui-monospace,Consolas,monospace;background:#fff;padding:8px 10px;border-radius:8px;display:inline-block}}
.btn{{display:inline-block;background:#ec4899;color:#fff;padding:14px 20px;border-radius:10px;text-decoration:none;margin-top:16px;border:0;cursor:pointer;font-size:16px;font-weight:700}}
.status{{padding:4px 10px;border-radius:999px;background:#fef3c7;color:#92400e;display:inline-block;font-size:13px;font-weight:700}}.status.paid{{background:#dcfce7;color:#166534}}.status.review{{background:#dbeafe;color:#1e40af}}
.notice{{margin-top:16px;padding:12px 14px;border-radius:10px;background:#dbeafe;color:#1e40af}}.paid-note{{background:#dcfce7;color:#166534}}
@media(max-width:640px){{.kaspi{{grid-template-columns:1fr}}.qr{{width:100%;height:auto;max-height:280px}}}}
</style></head><body><div class="page">
<h1>{h(shop.name or "")}</h1>
<div class="muted">Счёт №{o.id} · <span class="status {status_class}">{h(_status_label(o.status))}</span></div>
<table><tr><th>Товар</th><th>Кол-во</th><th>Цена</th></tr>{items_html}</table>
<div class="total">Итого: {h(_money(o.total))} {currency}</div>
<div class="muted" style="margin-top:8px">Имя: {h(str(details.get("name") or "-"))} ·
 Телефон: {h(str(details.get("phone") or "-"))}<br>
 Адрес: {h(str(details.get("address") or "-"))} ·
 Доставка: {h(str(details.get("delivery_date") or "-"))}</div>
<div class="kaspi">
  <div>{qr_html}</div>
  <div>
    <h2 style="margin:0 0 8px">Оплата Kaspi</h2>
    <div class="muted">{h(instructions)}</div>
    <div style="margin-top:14px">Получатель</div>
    <div class="copy">{h(kaspi_name or "-")}</div>
    <div>Телефон Kaspi</div>
    <div class="copy">{h(kaspi_phone or "Не настроен")}</div>
    <div>Комментарий к платежу</div>
    <div class="comment">{h(pay_comment)}</div>
  </div>
</div>
{button_html}
{review_html}
{paid_html}
</div></body></html>"""


@router.post("/pay/{order_id}/confirm", response_class=HTMLResponse)
@limiter.limit(settings.rate_limit_pay_confirm)
def pay_confirm(
    request: Request,
    order_id: int,
    t: str = Query(default=""),
    db: Session = Depends(get_db),
):
    o = db.get(models.Order, order_id)
    if not o:
        raise HTTPException(404)
    _verify_or_404(o, t)
    if o.status not in {"paid", "payment_review"}:
        o.status = "payment_review"
        if o.conversation_id:
            conv = db.get(models.Conversation, o.conversation_id)
            if conv:
                conv.status = "payment_review"
                db.add(
                    models.Message(
                        conversation_id=conv.id,
                        role="system",
                        text=f"Клиент сообщил об оплате Kaspi по заказу №{o.id}; нужна проверка менеджера",
                    )
                )
        db.commit()
        log_action(db, "kaspi_payment_reported", shop_id=o.shop_id, request=request,
                   meta={"order_id": o.id, "total": o.total})
    return HTMLResponse(f"<h2>Спасибо! Заказ №{o.id} отправлен менеджеру на проверку оплаты Kaspi.</h2>")
