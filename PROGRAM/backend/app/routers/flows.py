from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import log_action
from ..auth import current_shop
from ..database import get_db
from ..flow_engine import validate_graph
from ..seed import build_agent_flow

router = APIRouter(prefix="/api/flows", tags=["flows"])


def _check_graph(graph: dict) -> None:
    errors = validate_graph(graph or {})
    if errors:
        raise HTTPException(422, {"detail": "Invalid graph", "errors": errors})


@router.get("", response_model=list[schemas.FlowOut])
def list_flows(db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    return db.query(models.Flow).filter_by(shop_id=shop.id).order_by(models.Flow.id.desc()).all()


@router.post("", response_model=schemas.FlowOut)
def create_flow(payload: schemas.FlowCreate, db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    _check_graph(payload.graph or {})
    f = models.Flow(shop_id=shop.id, **payload.model_dump())
    db.add(f); db.commit(); db.refresh(f)
    return f


def _own(db, shop, fid) -> models.Flow:
    f = db.get(models.Flow, fid)
    if not f or f.shop_id != shop.id:
        raise HTTPException(404)
    return f


@router.get("/{fid}", response_model=schemas.FlowOut)
def get_flow(fid: int, db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    return _own(db, shop, fid)


@router.put("/{fid}", response_model=schemas.FlowOut)
def update_flow(fid: int, payload: schemas.FlowCreate, db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    _check_graph(payload.graph or {})
    f = _own(db, shop, fid)
    for k, v in payload.model_dump().items():
        setattr(f, k, v)
    db.commit(); db.refresh(f); return f


@router.delete("/{fid}")
def delete_flow(fid: int, db: Session = Depends(get_db), shop: models.Shop = Depends(current_shop)):
    f = _own(db, shop, fid)
    db.delete(f); db.commit()
    return {"ok": True}


@router.post("/seed-agent")
def seed_agent_flow(
    request: Request,
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    """Создаёт новый agent-флоу для магазина и делает его активным.
    Старые флоу остаются, но деактивируются."""
    db.query(models.Flow).filter_by(shop_id=shop.id).update({"is_active": False})
    f = models.Flow(
        shop_id=shop.id,
        name="AI-агент",
        description="Полноценный LLM-агент: сам ведёт диалог, собирает данные, создаёт счёт.",
        is_active=True,
        graph=build_agent_flow(shop.name),
    )
    db.add(f); db.commit(); db.refresh(f)
    log_action(db, "flow_seed_agent", shop_id=shop.id, request=request, meta={"flow_id": f.id})
    return {"ok": True, "flow_id": f.id}


@router.post("/{fid}/activate")
def activate(
    request: Request,
    fid: int,
    db: Session = Depends(get_db),
    shop: models.Shop = Depends(current_shop),
):
    # Транзакционно: блокируем магазин, деактивируем остальные, активируем выбранный.
    f = _own(db, shop, fid)
    db.query(models.Flow).filter_by(shop_id=shop.id).update({"is_active": False})
    f.is_active = True
    db.commit()
    log_action(db, "flow_activate", shop_id=shop.id, request=request, meta={"flow_id": fid})
    return {"ok": True}
