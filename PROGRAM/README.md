# 🌸 Floral AI — SaaS для AI-продаж цветов

Мультитенантный веб-сервис: каждый цветочный магазин регистрируется, подключает
свой **WhatsApp** (QR по номеру) и **Instagram** (логин/пароль), настраивает
сценарий диалога в визуальном редакторе — и AI ведёт клиентов от "Здравствуйте"
до оплаты счёта.

## Возможности
- 🏢 **Мультитенантность** — каждый магазин изолирован (`shop_id` везде)
- 🔐 **Auth** — email/пароль, JWT в httpOnly+SameSite=Strict cookie, ротация при login, отзыв при logout
- 🎨 **Визуальный редактор** (React Flow): 10 типов узлов
- 🤖 **AI** — Gemini или OpenAI, ключ задаётся в настройках магазина (шифруется Fernet)
- 📱 **WhatsApp** — `whatsapp-web.js`, каждый магазин = свой `clientId`, webhook защищён HMAC + timestamp
- 📸 **Instagram** — код есть (`instagrapi`), но **роуты сейчас отключены** (Meta блокирует
  логины с серверных IP, нужен residential-прокси). См. `backend/app/routers/channels.py`,
  `backend/app/channels/instagram.py`.
- 🧾 **Счета** — автосоздание заказа + публичная **подписанная** ссылка с TTL (HMAC, отдельный
  `PAY_SIGNING_KEY`, срок жизни 7 дней). Кнопка «Оплатить» в шаблоне — **демо**, для prod
  принимайте `paid` только из webhook платёжного провайдера.
- 🧪 **Симулятор** — тест сценариев без реальных каналов

## Архитектура
```
 ┌──────────┐   HTTPS   ┌────────┐   ┌──────────┐
 │  Browser ├──────────▶│ Caddy  │──▶│ Frontend │  (React SPA, nginx)
 └──────────┘           │(HTTPS) │   └──────────┘
                        │        │   ┌──────────┐     ┌──────────┐
                        │        │──▶│ Backend  │────▶│ Postgres │
                        └────────┘   │ FastAPI  │     └──────────┘
                                     └────┬─────┘
                                          │           ┌────────────┐
                                          ├──────────▶│ WA bridge  │ (Node+Chromium)
                                          │           │ per-shop   │
                                          │           └────────────┘
                                          │
                                          └── instagrapi (in-process threads, per-shop)
```

## Production deploy (Docker Compose + Caddy + Postgres + HTTPS)

Требования на сервере: Docker + docker-compose, домен, указывающий на IP.

```bash
git clone <repo> floral-ai && cd floral-ai
cp .env.example .env
# отредактируйте .env: укажите DOMAIN, JWT_SECRET, WA_BRIDGE_SECRET,
# GEMINI_API_KEY (глобальный дефолт, опционально)
docker compose up -d --build
```

Caddy автоматически получит HTTPS-сертификат Let's Encrypt для `DOMAIN`.
На `localhost` (для теста) откроется по HTTP без SSL.

**Админ URLs:**
- `https://your-domain/` — UI магазинов (Login/Signup)
- `https://your-domain/api/docs` — Swagger документация API
- `https://your-domain/pay/{id}` — публичная страница счёта

## Локальный запуск без Docker (для разработки)

1. **Backend**
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   uvicorn app.main:app --reload --port 8000
   ```
2. **Frontend**
   ```powershell
   cd frontend
   npm install
   npm run dev
   ```
3. **WhatsApp bridge**
   ```powershell
   cd whatsapp-bridge
   npm install
   Copy-Item .env.example .env
   npm start
   ```

Или одной командой: **`.\start.ps1`** (см. ниже).

## Первое использование
1. Откройте `/signup` → зарегистрируйтесь как магазин
2. **Настройки** → вставьте свой Gemini/OpenAI API ключ
3. **Каналы → WhatsApp** → нажмите «Подключить» → сканируйте QR с телефона
4. **Сценарии** → отредактируйте демо-сценарий под свой магазин
5. Клиенты пишут вам в WhatsApp — бот отвечает и доводит до счёта
6. Смотрите заказы в разделе **Заказы**, диалоги — в разделе **Диалоги**
   (там же кнопки «Забрать диалог» / «Вернуть AI» / «Ответить»)

## Структура проекта
```
PROGRAM/
├── backend/                    FastAPI + SQLAlchemy
│   ├── app/
│   │   ├── main.py
│   │   ├── auth.py             JWT + bcrypt + current_shop
│   │   ├── models.py           Shop, Flow, Customer, Conversation, Message, Order, Product
│   │   ├── ai.py               Gemini + OpenAI
│   │   ├── flow_engine.py      исполнение графа
│   │   ├── invoice.py          создание заказов
│   │   ├── dispatcher.py       входящие сообщения → Flow Engine
│   │   ├── seed.py             демо-флоу + товары при регистрации
│   │   ├── channels/
│   │   │   ├── whatsapp.py     клиент к Node-мосту
│   │   │   └── instagram.py    IGManager: по IGSession на магазин
│   │   └── routers/
│   │       ├── auth.py         signup/login/me
│   │       ├── flows.py
│   │       ├── orders.py
│   │       ├── conversations.py
│   │       ├── channels.py     WA/IG connect/status/qr/logout + webhook
│   │       └── pay.py          страница счёта
│   ├── Dockerfile
│   └── requirements.txt
├── whatsapp-bridge/            Node + whatsapp-web.js, мульти-сессии
│   ├── server.js
│   └── Dockerfile
├── frontend/                   React + Vite + React Flow
│   ├── src/
│   │   ├── App.jsx             приватные роуты
│   │   ├── auth.js             токен в localStorage
│   │   ├── api.js              fetch + Authorization
│   │   └── pages/              Login, Signup, FlowsList, FlowEditor,
│   │                           Simulator, Conversations, Orders,
│   │                           Products, Channels, Settings
│   ├── Dockerfile
│   └── nginx.conf
├── Caddyfile                   reverse proxy + HTTPS
├── docker-compose.yml
└── .env.example
```

## Безопасность
- **JWT_SECRET**, **WA_BRIDGE_SECRET**, **SECRET_ENCRYPTION_KEY**, **PAY_SIGNING_KEY**
  обязательно сгенерируйте случайными (≥32 символа). При `ENV=prod` приложение
  **падает на старте**, если ключевые секреты дефолтные / пустые.
- Пароли магазинов хешируются `bcrypt`.
- AI-ключи и IG-прокси в БД зашифрованы Fernet (`SECRET_ENCRYPTION_KEY`).
- JWT — в httpOnly cookie, `SameSite=Strict`, `Secure` в prod. Логин **ротирует** все ранее
  выпущенные токены (через `Shop.tokens_valid_after`), logout отзывает текущий jti.
- Webhook от WA-моста: HMAC-SHA256 от `<timestamp>.<body>` + проверка skew ≤ 5 мин (защита
  от replay). Legacy подпись по чистому body — только в dev.
- Pay-ссылки подписаны HMAC отдельным ключом (`PAY_SIGNING_KEY`, не пересекается с JWT)
  и содержат `exp` (по умолчанию 7 дней). Демо-кнопка «Оплатить» — для prod заменить на
  webhook платёжного провайдера.
- HTML-страница счёта эскейпит все пользовательские поля (XSS-защита).
- Caddy ставит CSP / HSTS / X-Frame-Options / Referrer-Policy.
- На каждое чувствительное действие пишется `AuditLog` (signup, login [success/failed],
  logout, settings_update, wa_connect/logout, flow_activate/seed_agent,
  conv_takeover/resume, manager_reply, pay_confirm_demo).
- Per-conversation in-process lock защищает state-машину от гонок при пачках сообщений
  от одного клиента (для multi-instance нужен Redis advisory lock — см. `AGENTS.md`).
- Сессии WhatsApp — в `.wa-sessions/shop_{id}/`, docker volume. При рестарте backend
  делается sync статуса с мостом (см. `_sync_wa_state` в `app/main.py`).
- Для продакшна: шифруйте volume на диске (LUKS), делайте бэкапы Postgres.

## API (auth — httpOnly-cookie или `Authorization: Bearer <JWT>`; `/auth/*`, `/pay/*` — публично)
**Auth**
- `POST /api/auth/signup` `{email, password, name}` → `{access_token}` + cookie
- `POST /api/auth/login` → `{access_token}` + cookie (предыдущие токены инвалидируются)
- `POST /api/auth/logout` (отзывает текущий jti)
- `GET/PUT /api/auth/me`

**Flows**
- `GET/POST /api/flows`, `GET/PUT/DELETE /api/flows/{id}`
- `POST /api/flows/{id}/activate`
- `POST /api/flows/seed-agent` (создать новый AI-агент-флоу и активировать)

**Orders / Products**
- `GET /api/orders`, `GET /api/orders/{id}`, `POST /api/orders/{id}/status?status=...`
- `GET /api/orders/products/all`, `POST /api/orders/products`,
  `PUT/DELETE /api/orders/products/{id}`

**Conversations**
- `GET /api/conversations[?status=...]`, `GET /api/conversations/{id}`
- `POST /api/conversations/sim` — симулятор
- `POST /api/conversations/{id}/takeover` / `resume` / `reply` — управление менеджером

**Channels**
- `POST /api/channels/whatsapp/connect|logout`, `GET /api/channels/whatsapp/status|qr`
- **Webhook** от WA-моста: `POST /api/channels/whatsapp/webhook`
  (headers `X-Bridge-Signature` + `X-Bridge-Timestamp`, HMAC-SHA256 от `<ts>.<body>`,
  допустимое расхождение часов — `WA_WEBHOOK_MAX_SKEW`, по умолчанию 300 сек)
- Instagram-роуты сейчас отключены (см. «Возможности»).

**Pay (public)**
- `GET /pay/{order_id}?t=<token>` — HTML-страница счёта (HMAC + exp в токене)
- `POST /pay/{order_id}/confirm?t=<token>` — демо-подтверждение; в проде заменяется
  на webhook платёжного провайдера

## Замечания про неофициальные API
- **WhatsApp Web** (`whatsapp-web.js`) — официально не поддерживается, Meta может
  банить. Для серьёзной коммерции рекомендуем переход на WhatsApp **Cloud API**.
- **Instagram** (`instagrapi`) — использует мобильный API, возможны challenge-коды
  и лимиты. Для надёжности — Instagram Graph API (через Meta Business).
- Архитектура готова к замене: `channels/whatsapp.py` и `channels/instagram.py`
  — изолированные адаптеры.

## Монетизация
Добавить Stripe Subscriptions:
1. Модель `Subscription(shop_id, plan, status, current_period_end)`
2. Middleware: если подписка истекла — блокировать API кроме `/auth/*` и `/billing/*`
3. Webhook Stripe → обновляет статус подписки

## Dev: запуск одной командой (Windows)
```powershell
.\start.ps1       # первый раз: поставит зависимости, запустит всё, откроет браузер
.\start.ps1 -Stop # остановит
```
