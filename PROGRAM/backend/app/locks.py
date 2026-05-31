"""Advisory locks для сериализации обработки сообщений по клиентам.

Если задан REDIS_URL — используем `SET NX PX` + Lua-unlock как distributed lock.
Иначе — fallback на in-process threading.Lock (ОК для single-process dev).

Контракт: контекст-менеджер, который БЛОКИРУЕТ до получения lock'а (с разумным
ожиданием и TTL, чтобы повисший воркер не залочил очередь навсегда).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager

from .config import settings

log = logging.getLogger(__name__)

# Параметры по умолчанию: lock держится не дольше 60 сек (на случай падения воркера),
# ждать получения lock'а — до 30 сек (далее лучше отдать ошибку, чем висеть).
_DEFAULT_TTL_MS = 60_000
_DEFAULT_WAIT_S = 30.0
_POLL_S = 0.05

# Lua-скрипт: атомарный unlock, освобождаем только если значение совпадает с нашим токеном.
_UNLOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

_redis_client = None
_redis_init_lock = threading.Lock()


def _get_redis():
    """Лениво создаём Redis-клиент. Возвращаем None, если REDIS_URL пуст
    или клиент недоступен (тогда падаем в process-fallback)."""
    global _redis_client
    if not settings.redis_url:
        return None
    if _redis_client is not None:
        return _redis_client
    with _redis_init_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(settings.redis_url, socket_timeout=2)
            client.ping()
            _redis_client = client
            log.info("locks: using Redis at %s", settings.redis_url)
        except Exception:
            log.exception("locks: Redis init failed, falling back to in-process locks")
            _redis_client = None
    return _redis_client


# In-process fallback: по одному Lock на ключ.
_proc_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_proc_locks_guard = threading.Lock()


def _get_proc_lock(key: str) -> threading.Lock:
    with _proc_locks_guard:
        return _proc_locks[key]


@contextmanager
def advisory_lock(key: str, ttl_ms: int = _DEFAULT_TTL_MS, wait_s: float = _DEFAULT_WAIT_S):
    """Берём lock на `key`. Освобождаем по выходу из контекста.

    Поведение при таймауте ожидания: пишем warning, но всё равно входим в критическую
    секцию (как и threading.Lock). Это сознательный компромисс — лучше двойная обработка
    одного сообщения (защищена идемпотентностью), чем потерянное сообщение.
    """
    redis_cli = _get_redis()
    if redis_cli is None:
        lock = _get_proc_lock(key)
        lock.acquire()
        try:
            yield "process"
        finally:
            lock.release()
        return

    redis_key = f"lock:{key}"
    token = uuid.uuid4().hex
    deadline = time.monotonic() + wait_s
    acquired = False
    while True:
        try:
            ok = redis_cli.set(redis_key, token, nx=True, px=ttl_ms)
        except Exception:
            log.exception("locks: redis SET failed, falling back to process lock")
            lock = _get_proc_lock(key)
            lock.acquire()
            try:
                yield "process-fallback"
            finally:
                lock.release()
            return
        if ok:
            acquired = True
            break
        if time.monotonic() >= deadline:
            log.warning("locks: wait timeout for key=%s — entering critical section anyway", key)
            break
        time.sleep(_POLL_S)
    try:
        yield "redis" if acquired else "redis-timeout"
    finally:
        if acquired:
            try:
                redis_cli.eval(_UNLOCK_LUA, 1, redis_key, token)
            except Exception:
                log.exception("locks: redis unlock failed key=%s", key)
