# AGENTS.md — рабочие заметки для AI-ассистентов и разработчиков

## Запуск тестов

```powershell
cd backend
.\.venv\Scripts\python -m pytest          # все тесты (≈ 57)
.\.venv\Scripts\python -m pytest -x       # стоп на первой ошибке
.\.venv\Scripts\python -m pytest tests/test_pay_token.py -v
```

Тесты используют SQLite в `tempfile`, `ENV=test` (см. `tests/conftest.py`).
Никакие реальные AI/WhatsApp/IG не дёргаются — есть фолбэки/эвристики.

## Линтер

```powershell
cd backend
.\.venv\Scripts\python -m ruff check app/
```

Конфиг в `backend/pyproject.toml`. Frontend — ESLint пока не настроен (TODO).

## Запуск локально

```powershell
.\start.ps1            # ставит зависимости, запускает backend+frontend+wa-bridge
.\start.ps1 -Stop      # останавливает
```

В Docker (prod-схема):

```powershell
docker compose up -d --build
```

Алембик-миграции применяются в `CMD` Dockerfile-а backend'а автоматически.
В dev на sqlite миграции **не запускаются**, схема создаётся через `Base.metadata.create_all`
в `app/main.py`.

## Архитектурные инварианты (которые легко сломать)

1. **`shop_id` присутствует везде** — мультитенантность держится на этом. Любой новый эндпоинт
   обязан фильтровать по `shop.id` (см. `_own*` helpers в роутерах).
2. **AI-ключ в БД зашифрован** — поле `Shop.ai_api_key` имеет тип `EncryptedString` (Fernet).
   Без `SECRET_ENCRYPTION_KEY` в prod backend не стартует.
3. **JWT идёт в httpOnly cookie + опционально Authorization header**. `SameSite=Strict`.
   Любой новый login-флоу должен вызывать `rotate_tokens_for_shop` перед выдачей токена.
4. **Webhook от WA-моста** проверяет `X-Bridge-Signature` = HMAC(secret, `ts.body`) и skew.
   Если меняете формат полезной нагрузки — синхронно правьте `whatsapp-bridge/server.js`
   (`sendWebhook`) и `backend/app/routers/channels.py` (`wa_webhook`).
5. **Pay-токены** — отдельный `PAY_SIGNING_KEY` (или дериват от JWT в dev). Формат
   `<exp_hex>.<sig16>`. Не принимайте `paid` без проверки подписи.
6. **Per-conversation lock** в `dispatcher.py` — все вебхуки/IG-сообщения от одного клиента
   сериализуются. Если выносить обработку в внешнюю очередь — нужен Redis advisory lock.
7. **Outbox-доставка** в `dispatcher.py` пытается переслать ВСЕ ещё не доставленные bot-сообщения
   диалога на каждом новом инкаминге (а не только новые). Это «бедняцкий» retry — клиент
   получит то, что бот накопил, как только канал поднимется.
8. **Inbox persistence**: каждое входящее (WA/IG) сохраняется СИНХРОННО в `incoming_messages`
   до фоновой обработки (`dispatcher.persist_incoming`). После успешной обработки
   `_mark_processed` ставит `status='processed'`. Если падаем — scheduler-job
   `retry_pending_inbox` каждые 30 сек подбирает pending-записи с `attempts < 5`.
   Не убирайте этот вызов из `wa_webhook` / IG-поллера — это страховка от потери сообщения.
9. **Redis (опционально)**: если задан `REDIS_URL`, то на нём работают slowapi rate-limit
   (`storage_uri`) и advisory-locks per-conversation (`app/locks.py`). Если переменная пуста —
   откатываемся на in-memory / process-lock (ОК для dev/single-worker, НЕ для prod с
   `--workers > 1`). В compose Redis заведён с persistence (`--appendonly yes`) и LRU.
10. **Audit sanitizer**: `audit.sanitize_meta` всегда фильтрует значения ключей, попадающих
    под regex `(api[_-]?key|secret|password|token|proxy|authorization|cookie|bearer)`,
    заменяя их на `***redacted***`. Булевы флаги (`*_changed: True`) остаются. Если добавляете
    новое поле с секретом — назовите ключ согласно паттерну, иначе значение пройдёт в БД.

## Известные TODO (приоритет ↓)

### Высокий
- ~~Redis-backed rate limit и locks~~ — сделано. `slowapi.Limiter(storage_uri=REDIS_URL)`,
  `app/locks.py advisory_lock(...)` (SET NX PX + Lua unlock) с in-process fallback.
- ~~Outbox-queue~~ — сделано через `incoming_messages` (persist синхронно в webhook,
  `retry_pending_inbox` каждые 30 сек). Это не полноценная очередь, но потерю сообщения
  при крэше backend между ACK и `handle_incoming` закрывает.
- **Stripe / YooKassa интеграция.** Сейчас `/pay/{id}/confirm` принимает оплату клиента по
  HMAC-ссылке (Kaspi-флоу). Решение `kaspi-only` зафиксировано — провайдерские webhooks
  не нужны. Если потом понадобится Stripe — нужен endpoint `/api/pay/webhook/stripe` с
  проверкой `Stripe-Signature` (см. AGENTS-историю).
- ~~Шифрование payload-секретов на logging-уровне~~ — сделано: `audit.sanitize_meta` затирает
  значения ключей по regex (api_key|secret|password|token|proxy|authorization|cookie|bearer)
  на `***redacted***`. Регрессионный тест `tests/test_audit_sanitizer.py`.

### Средний
- **Instagram-канал восстановить.** Код в `app/channels/instagram.py` живой, поля `Shop.ig_*`
  есть, миграция применена. Не хватает:
  - раскомментировать IG-роуты в `routers/channels.py` и добавить `api.ig.*` во `frontend/src/api.js`
  - `IGCard` в `frontend/src/pages/Channels.jsx`
  - auto-restore IG-сессий при старте backend (как `_sync_wa_state` для WA), используя
    сохранённый файл сессии в `ig_sessions/shop_{id}.json`
  - требовать residential/mobile прокси (`Shop.ig_proxy`), иначе Meta блокирует серверные IP.
- **ESLint + Prettier во фронте**, frontend-тесты (vitest).
- **Healthcheck для каддэйных зависимостей.** Frontend и backend имеют HEALTHCHECK в
  Dockerfile, Caddy ждёт `service_healthy`. Если вдруг health-эндпоинт сломан — Caddy
  не поднимется. Полезно добавить fallback `condition: service_started` или таймауты.
- **Аналитика в UI.** AuditLog пишется в БД, но не отображается. Полезно: dashboard «диалогов в день»,
  «конверсия в счёт», «конверсия в paid».
- **Расширенные unit-тесты flow_engine** на агентский узел (`agent.py`, 289 строк): tool-call
  limit, защита от prompt-injection, корректное завершение через `pending_payment`.

### Низкий
- ~~Деприкейтнутые `class Config:`~~ — переведено на `model_config = ConfigDict(...)`.
- `instagrapi` пинит `pydantic==2.7.1`, но в окружении Python 3.13 ставится 2.13.x — pip-конфликт
  игнорируется. Когда IG-канал восстановим, оценить совместимость.
- ~~Docker compose: `deploy.resources.limits`~~ — добавлено для всех сервисов.
- ~~Backup-сервис Postgres~~ — `db-backup` service, ежедневный `pg_dump -Fc` в `db-backups` volume,
  retention 14 дней (env `BACKUP_RETENTION_DAYS`).
- ~~WA bridge non-root~~ — в Dockerfile добавлен `wabridge:1001` + `USER wabridge`.
- ~~Удалить `Документ Microsoft Word.docx` и `.pids.json`~~ — удалены.

## Сложные места, в которых уже наступали

- **DateTime + SQLite** возвращает naive datetime, хотя поле объявлено как `DateTime(timezone=True)`.
  Везде, где сравниваем с epoch-iat из JWT, обязательно `tva.replace(tzinfo=UTC)` до `.timestamp()`.
  Иначе на хосте с не-UTC timezone получите некорректные результаты (см. `auth.current_shop`).
- **`int(iat) < tva_ts` с tolerance ±2 сек.** Иначе ротация валит свежий токен из-за гонок
  записи tokens_valid_after и create_access_token в одну секунду.
- **`run_conversation` safety guard = 50 шагов.** При срабатывании теперь переводим в `handoff`
  и логируем `flow safety guard hit`. Не делайте циклов в графе.
- **WA bridge auto-restore** делается через сканирование папки `.wa-sessions/session-shop_*`
  при старте. Если volume пустой — backend думает, что WA подключён (по БД), а реально — нет.
  `_sync_wa_state` в `app/main.py` корректирует флаг.
