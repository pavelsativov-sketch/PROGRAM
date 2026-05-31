"""Rate-limiter на slowapi.

Если задан REDIS_URL — лимиты шарятся между воркерами/инстансами через Redis.
Иначе — in-memory (ОК для dev и single-worker; в prod с --workers > 1 это
означает, что каждый воркер считает лимит отдельно).
"""
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings

log = logging.getLogger(__name__)

_kwargs: dict = {"key_func": get_remote_address, "default_limits": []}
if settings.redis_url:
    _kwargs["storage_uri"] = settings.redis_url
    log.info("rate-limit: using Redis storage at %s", settings.redis_url)
else:
    log.info("rate-limit: using in-memory storage (set REDIS_URL for multi-worker)")

limiter = Limiter(**_kwargs)
