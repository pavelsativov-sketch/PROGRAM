from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import current_shop
from ..database import get_db

router = APIRouter(prefix="/api/orders", tags=["orders"])

IMAGE_TYPES = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"RIFF": "webp",
}


def _detect_image_ext(raw: bytes) -> str | None:
    for sig, ext in IMAGE_TYPES.items():
        if raw.startswith(sig):
            if ext == "webp" and raw[8:12] != b"WEBP":
                return None
            return ext
    return None


@router.get("", response_model=list[schemas.OrderOut])
def list_orders(db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    return db.query(models.Order).filter_by(shop_id=shop.id).order_by(models.Order.id.desc()).all()


def _own_order(db, shop, oid) -> models.Order:
    o = db.get(models.Order, oid)
    if not o or o.shop_id != shop.id:
        raise HTTPException(404)
    return o


@router.get("/{oid}", response_model=schemas.OrderOut)
def get_order(oid: int, db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    return _own_order(db, shop, oid)


@router.post("/{oid}/status")
def set_status(oid: int, status: str, db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    o = _own_order(db, shop, oid)
    prev = o.status
    o.status = status
    db.commit()
    # Уведомляем магазин при подтверждении оплаты — самое важное событие.
    if status == "paid" and prev != "paid":
        try:
            from .. import notifier
            notifier.notify_paid(shop, o)
        except Exception:
            pass
        try:
            from .. import notifications
            notifications.record(
                db, shop,
                type="order_paid",
                severity="info",
                title=f"Оплачен заказ №{o.id} — {o.total:.0f} {shop.currency}",
                body=f"Клиент: {(o.details or {}).get('name') or '—'}",
                link="/orders",
                meta={"order_id": o.id},
                telegram=False,
            )
            db.commit()
        except Exception:
            pass
    return {"ok": True}


# Products
@router.get("/products/all", response_model=list[schemas.ProductOut])
def products(db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    return db.query(models.Product).filter_by(shop_id=shop.id).order_by(models.Product.id.desc()).all()


@router.post("/products", response_model=schemas.ProductOut)
def create_product(p: schemas.ProductIn, db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    x = models.Product(shop_id=shop.id, **p.model_dump())
    db.add(x); db.commit(); db.refresh(x); return x


def _own_product(db, shop, pid) -> models.Product:
    x = db.get(models.Product, pid)
    if not x or x.shop_id != shop.id:
        raise HTTPException(404)
    return x


@router.put("/products/{pid}", response_model=schemas.ProductOut)
def update_product(pid: int, p: schemas.ProductIn, db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    x = _own_product(db, shop, pid)
    for k, v in p.model_dump().items():
        setattr(x, k, v)
    db.commit(); db.refresh(x); return x


@router.delete("/products/{pid}")
def delete_product(pid: int, db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    x = _own_product(db, shop, pid)
    db.delete(x); db.commit(); return {"ok": True}


@router.post("/products/upload")
async def upload_product_image(
    file: UploadFile = File(...),
    shop: models.Shop = Depends(current_shop),
):
    raw = await file.read()
    if len(raw) > 6 * 1024 * 1024:
        raise HTTPException(400, "Изображение слишком большое, максимум 6 МБ")
    ext = _detect_image_ext(raw)
    if not ext:
        raise HTTPException(400, "Загрузите корректное изображение JPG, PNG или WebP")
    upload_dir = Path(__file__).resolve().parent.parent.parent / "uploads" / f"shop_{shop.id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.{ext}"
    path = upload_dir / filename
    path.write_bytes(raw)
    return {"url": f"/uploads/shop_{shop.id}/{filename}"}
