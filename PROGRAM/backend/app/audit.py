"""Helpers для записи аудита. Никогда не падаем, аудит не блокирует бизнес-логику.

Sanitizer: запрещаем класть в `meta` значения чувствительных полей (api-ключей,
паролей, прокси-строк). Любая попытка сохранения значения такого ключа заменяется
на маркер "***redacted***" — даже если разработчик случайно передал raw-значение.
"""
from __future__ import annotations

import logging
import re

from fastapi import Request
from sqlalchemy.orm import Session

from . import models

log = logging.getLogger(__name__)

# Ключи, чьи значения никогда не должны попадать в audit.meta.
_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|secret|password|token|proxy|authorization|cookie|bearer)",
    re.IGNORECASE,
)
_REDACTED = "***redacted***"


def sanitize_meta(meta: dict | None) -> dict:
    """Возвращает копию meta, в которой значения по чувствительным ключам затёрты.
    Допускаются boolean-флаги вида `<field>_changed: True/False` — они информативны
    и не несут секрета."""
    if not meta:
        return {}
    out: dict = {}
    for k, v in meta.items():
        key = str(k)
        # Разрешаем булевые флаги факта изменения (..._changed).
        if isinstance(v, bool):
            out[key] = v
            continue
        if _SENSITIVE_KEY_RE.search(key):
            out[key] = _REDACTED
            continue
        # Если значение — dict/list, рекурсивно очищаем по ключам.
        if isinstance(v, dict):
            out[key] = sanitize_meta(v)
        elif isinstance(v, list):
            out[key] = [sanitize_meta(x) if isinstance(x, dict) else x for x in v]
        else:
            out[key] = v
    return out


def log_action(
    db: Session,
    action: str,
    shop_id: int | None = None,
    request: Request | None = None,
    meta: dict | None = None,
) -> None:
    try:
        ip = ""
        ua = ""
        if request is not None:
            ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
                request.client.host if request.client else ""
            )
            ua = request.headers.get("user-agent", "")[:255]
        db.add(
            models.AuditLog(
                shop_id=shop_id,
                action=action,
                ip=ip[:64],
                user_agent=ua,
                meta=sanitize_meta(meta),
            )
        )
        db.commit()
    except Exception:
        log.exception("audit log failed")
        try:
            db.rollback()
        except Exception:
            pass
