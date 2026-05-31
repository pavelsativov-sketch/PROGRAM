import logging
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import models  # noqa: F401
from .config import settings
from .database import Base, SessionLocal, engine
from .logging_config import setup_logging
from .rate_limit import limiter
from .routers import (
    analytics,
    auth,
    channels,
    conversations,
    customers,
    flows,
    notifications,
    orders,
    pay,
)

setup_logging()
log = logging.getLogger(__name__)

# Для dev/тестов на sqlite — авто-создание схемы (alembic не запускается из тестов).
# В prod схему ведёт alembic (см. Dockerfile / start.ps1).
if settings.database_url.startswith("sqlite"):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        shop_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(shops)").fetchall()}
        for name, ddl in {
            "kaspi_phone": "ALTER TABLE shops ADD COLUMN kaspi_phone VARCHAR(32) DEFAULT ''",
            "kaspi_name": "ALTER TABLE shops ADD COLUMN kaspi_name VARCHAR(255) DEFAULT ''",
            "kaspi_qr_url": "ALTER TABLE shops ADD COLUMN kaspi_qr_url VARCHAR(512) DEFAULT ''",
            "payment_instructions": "ALTER TABLE shops ADD COLUMN payment_instructions TEXT DEFAULT ''",
            "business_hours": "ALTER TABLE shops ADD COLUMN business_hours JSON",
            "tg_bot_token": "ALTER TABLE shops ADD COLUMN tg_bot_token VARCHAR(256) DEFAULT ''",
            "tg_chat_id": "ALTER TABLE shops ADD COLUMN tg_chat_id VARCHAR(64) DEFAULT ''",
            "bot_enabled": "ALTER TABLE shops ADD COLUMN bot_enabled BOOLEAN DEFAULT 1",
            "daily_summary_hour": "ALTER TABLE shops ADD COLUMN daily_summary_hour INTEGER DEFAULT 21",
            "followup_enabled": "ALTER TABLE shops ADD COLUMN followup_enabled BOOLEAN DEFAULT 1",
        }.items():
            if name not in shop_cols:
                conn.exec_driver_sql(ddl)
        product_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(products)").fetchall()}
        for name, ddl in {
            "category": "ALTER TABLE products ADD COLUMN category VARCHAR(128) DEFAULT 'Bouquets'",
            "available_today": "ALTER TABLE products ADD COLUMN available_today BOOLEAN DEFAULT 1",
        }.items():
            if name not in product_cols:
                conn.exec_driver_sql(ddl)
        customer_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(customers)").fetchall()}
        for name, ddl in {
            "tags": "ALTER TABLE customers ADD COLUMN tags JSON",
            "notes": "ALTER TABLE customers ADD COLUMN notes TEXT DEFAULT ''",
            "important_dates": "ALTER TABLE customers ADD COLUMN important_dates JSON",
        }.items():
            if name not in customer_cols:
                conn.exec_driver_sql(ddl)


_scheduler: BackgroundScheduler | None = None


def _purge_expired_revoked_tokens() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        deleted = (
            db.query(models.RevokedToken)
            .filter(models.RevokedToken.expires_at.isnot(None))
            .filter(models.RevokedToken.expires_at < now)
            .delete(synchronize_session=False)
        )
        if deleted:
            db.commit()
            log.info("purged %d expired revoked tokens", deleted)
    except Exception:
        log.exception("purge_expired_revoked_tokens failed")
        db.rollback()
    finally:
        db.close()


def _sync_wa_state() -> None:
    """Сверяем shop.wa_connected с реальным статусом WA-моста на старте.
    Если мост говорит «disconnected» — сбрасываем флаг в БД."""
    try:
        from .channels.whatsapp import whatsapp
    except Exception:
        return
    db = SessionLocal()
    try:
        shops = db.query(models.Shop).filter(models.Shop.wa_connected == True).all()  # noqa: E712
        for s in shops:
            try:
                st = whatsapp.status(s.id) or {}
                if st.get("status") not in ("ready", "qr", "starting", "authenticated"):
                    s.wa_connected = False
                    log.info("WA sync: shop %s marked disconnected (bridge status=%s)", s.id, st.get("status"))
            except Exception:
                log.exception("WA sync failed for shop %s", s.id)
        db.commit()
    except Exception:
        log.exception("wa state sync failed")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _scheduler
    # Жёсткая проверка секретов в проде — на старте сервера, а не на импорте модуля.
    settings.validate_for_env()
    if _scheduler is None and settings.env != "test":
        from .dispatcher import retry_pending_inbox
        sch = BackgroundScheduler(daemon=True)
        sch.add_job(_purge_expired_revoked_tokens, "interval", hours=1, id="purge_revoked_tokens",
                    next_run_time=datetime.now(UTC))
        # Inbox-retry: каждые 30 сек добиваем pending-записи, которые остались после
        # перезапуска backend или из-за ошибок AI-обработки.
        sch.add_job(retry_pending_inbox, "interval", seconds=30, id="retry_pending_inbox",
                    next_run_time=datetime.now(UTC), max_instances=1, coalesce=True)
        # Мониторинг здоровья бота, сводки, напоминания и дожим брошенных диалогов.
        from . import monitoring
        sch.add_job(monitoring.check_bot_health, "interval", minutes=10, id="check_bot_health",
                    max_instances=1, coalesce=True)
        sch.add_job(monitoring.send_daily_summaries, "interval", minutes=30, id="send_daily_summaries",
                    max_instances=1, coalesce=True)
        sch.add_job(monitoring.check_reminders, "interval", hours=6, id="check_reminders",
                    next_run_time=datetime.now(UTC), max_instances=1, coalesce=True)
        sch.add_job(monitoring.followup_abandoned_dialogs, "interval", hours=2, id="followup_abandoned",
                    max_instances=1, coalesce=True)
        sch.start()
        _scheduler = sch
        # Sync WA state в фоне — чтобы не блокировать старт, если мост недоступен.
        sch.add_job(_sync_wa_state, "date", run_date=datetime.now(UTC), id="wa_state_sync")
    try:
        yield
    finally:
        if _scheduler is not None:
            _scheduler.shutdown(wait=False)
            _scheduler = None


app = FastAPI(title="Floral AI SaaS", version="1.2.0", lifespan=lifespan)

# Rate limit
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — только whitelisted origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Request-ID"],
)


@app.middleware("http")
async def request_id_mw(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    request.state.request_id = rid
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled error request_id=%s path=%s", rid, request.url.path)
        return JSONResponse({"detail": "Internal Server Error", "request_id": rid}, status_code=500)
    response.headers["X-Request-ID"] = rid
    # Базовые security-заголовки на уровне приложения (Caddy/nginx добавят свои поверх).
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.include_router(auth.router)
app.include_router(flows.router)
app.include_router(orders.router)
app.include_router(conversations.router)
app.include_router(channels.router)
app.include_router(customers.router)
app.include_router(analytics.router)
app.include_router(notifications.router)
app.include_router(pay.router)


@app.get("/api/health")
def health():
    return {"ok": True, "env": settings.env}


# SPA (prod build, на случай монолитной деплой-схемы)
uploads_dir = Path(__file__).resolve().parent.parent / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
