/**
 * Мульти-тенантный WhatsApp-мост.
 * Каждый магазин имеет свою WhatsApp Web сессию по clientId=shop_<id>.
 *
 * Endpoints (все требуют header X-Bridge-Secret):
 *   POST /shops/:id/connect   - инициализировать клиент (или получить существующего)
 *   GET  /shops/:id/status    - состояние: disconnected|qr|ready
 *   GET  /shops/:id/qr        - data-url QR (если status=qr)
 *   POST /shops/:id/send      - {to, text}
 *   POST /shops/:id/logout
 */
const crypto = require('crypto');
const fs = require('fs');
const express = require('express');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode');
const axios = require('axios');
require('dotenv').config();

/**
 * Найти исполняемый файл браузера (Chrome/Chromium/Edge) для puppeteer.
 * whatsapp-web.js → puppeteer-core, который НЕ скачивает Chrome автоматически
 * и не умеет читать PUPPETEER_EXECUTABLE_PATH сам — мы передаём его в Client.
 */
function detectBrowserExecutable() {
  const env = process.env.PUPPETEER_EXECUTABLE_PATH || process.env.CHROME_PATH;
  if (env && fs.existsSync(env)) return env;

  const candidates = [];
  if (process.platform === 'win32') {
    const pf = process.env['ProgramFiles'] || 'C:\\Program Files';
    const pf86 = process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)';
    const local = process.env['LocalAppData'] || '';
    candidates.push(
      `${pf}\\Google\\Chrome\\Application\\chrome.exe`,
      `${pf86}\\Google\\Chrome\\Application\\chrome.exe`,
      `${local}\\Google\\Chrome\\Application\\chrome.exe`,
      `${pf}\\Microsoft\\Edge\\Application\\msedge.exe`,
      `${pf86}\\Microsoft\\Edge\\Application\\msedge.exe`,
    );
  } else if (process.platform === 'darwin') {
    candidates.push(
      '/Applications/Google Chrome.applications/Contents/MacOS/Google Chrome',
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Chromium.app/Contents/MacOS/Chromium',
    );
  } else {
    candidates.push(
      '/usr/bin/chromium',
      '/usr/bin/chromium-browser',
      '/usr/bin/google-chrome',
      '/usr/bin/google-chrome-stable',
    );
  }
  for (const p of candidates) {
    try { if (p && fs.existsSync(p)) return p; } catch {}
  }
  return null;
}

const BROWSER_PATH = detectBrowserExecutable();
if (BROWSER_PATH) {
  console.log(`[WA bridge] using browser: ${BROWSER_PATH}`);
} else {
  console.warn(
    '[WA bridge] WARNING: Chrome/Chromium не найден. Задайте PUPPETEER_EXECUTABLE_PATH ' +
    'или установите Chrome. WhatsApp-сессии не запустятся.'
  );
}

const PORT = process.env.PORT || 3001;
const SECRET = process.env.BRIDGE_SECRET || 'change_me';
const WEBHOOK = process.env.BACKEND_WEBHOOK || 'http://localhost:8000/api/channels/whatsapp/webhook';
const ENV = (process.env.ENV || process.env.NODE_ENV || 'dev').toLowerCase();

const WEAK_SECRETS = new Set(['change_me', 'change_me_wa_bridge_random', '']);
if (WEAK_SECRETS.has(SECRET) || SECRET.length < 16) {
  if (ENV === 'prod' || ENV === 'production') {
    console.error('[WA bridge] FATAL: BRIDGE_SECRET is weak/default. Refusing to start in prod.');
    process.exit(1);
  } else {
    console.warn('[WA bridge] WARNING: BRIDGE_SECRET is weak/default — OK in dev, set a strong random secret in prod.');
  }
}

const app = express();
app.use(express.json({ limit: '1mb' }));

/** shop_id -> { client, status, qr, me } */
const sessions = new Map();

function safeEq(a, b) {
  const ab = Buffer.from(String(a || ''));
  const bb = Buffer.from(String(b || ''));
  if (ab.length !== bb.length) return false;
  return crypto.timingSafeEqual(ab, bb);
}

function auth(req, res, next) {
  if (!safeEq(req.header('X-Bridge-Secret'), SECRET)) {
    return res.status(401).json({ error: 'bad secret' });
  }
  next();
}

async function sendWebhook(payload) {
  try {
    const body = JSON.stringify(payload);
    // Подпись = HMAC(secret, "<ts>.<body>") — защита и от подмены, и от replay
    // (backend сверяет ts ± max_skew).
    const ts = Math.floor(Date.now() / 1000).toString();
    const signature = crypto.createHmac('sha256', SECRET).update(ts + '.' + body).digest('hex');
    await axios.post(WEBHOOK, body, {
      headers: {
        'X-Bridge-Secret': SECRET, // оставляем для обратной совместимости в dev
        'X-Bridge-Signature': signature,
        'X-Bridge-Timestamp': ts,
        'Content-Type': 'application/json',
      },
      timeout: 15000,
    });
  } catch (e) {
    console.error('[webhook]', e.message);
  }
}

function getOrCreate(shopId) {
  if (sessions.has(shopId)) return sessions.get(shopId);
  const sess = { status: 'starting', qr: null, me: null, client: null };
  const puppeteerOpts = {
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    headless: true,
  };
  if (BROWSER_PATH) puppeteerOpts.executablePath = BROWSER_PATH;
  const client = new Client({
    authStrategy: new LocalAuth({ clientId: `shop_${shopId}`, dataPath: './.wa-sessions' }),
    puppeteer: puppeteerOpts,
  });

  client.on('qr', async (qr) => {
    sess.qr = await qrcode.toDataURL(qr);
    sess.status = 'qr';
    console.log(`[shop ${shopId}] QR ready`);
  });

  client.on('loading_screen', (percent, message) => {
    console.log(`[shop ${shopId}] loading ${percent}% — ${message}`);
  });

  client.on('change_state', (state) => {
    console.log(`[shop ${shopId}] state -> ${state}`);
  });

  client.on('authenticated', () => {
    console.log(`[shop ${shopId}] authenticated (session valid)`);
  });

  client.on('ready', () => {
    sess.status = 'ready';
    sess.qr = null;
    sess.me = client.info?.wid?.user || null;
    console.log(`[shop ${shopId}] ready as`, sess.me);
    sendWebhook({ shop_id: shopId, event: 'ready', me: sess.me });
  });

  client.on('disconnected', (r) => {
    sess.status = 'disconnected';
    console.log(`[shop ${shopId}] disconnected`, r);
    sendWebhook({ shop_id: shopId, event: 'disconnected' });
  });

  // Диагностический лог КАЖДОГО события message_create — видно даже исходящие.
  client.on('message_create', (msg) => {
    console.log(
      `[shop ${shopId}] message_create from=${msg.from} to=${msg.to} ` +
      `fromMe=${msg.fromMe} type=${msg.type} body_len=${(msg.body || '').length}`
    );
  });

  // Какие отправители считаем валидными личными чатами.
  // - @c.us — классический формат (телефон).
  // - @lid — новый Linked-ID формат WhatsApp (для приватности контактов).
  // Группы (@g.us), broadcast (status@broadcast) и каналы (@newsletter) игнорируем.
  const isPrivateUser = (jid) =>
    !!jid && (jid.endsWith('@c.us') || jid.endsWith('@lid'));

  const onIncoming = async (msg) => {
    if (msg.fromMe || msg.isStatus) return;
    if (msg.from === 'status@broadcast') return;
    if (!isPrivateUser(msg.from)) return;
    if (msg.type && msg.type !== 'chat' && msg.type !== 'text') return;
    if (!msg.body) return;
    console.log(`[shop ${shopId}] incoming from=${msg.from} text=${msg.body.slice(0, 80)}`);
    await sendWebhook({
      shop_id: shopId,
      event: 'message',
      from: msg.from,
      text: msg.body,
      name: msg._data?.notifyName || '',
    });
  };
  client.on('message', onIncoming);
  // На некоторых сборках whatsapp-web.js входящее идёт ТОЛЬКО как message_received.
  client.on('message_received', onIncoming);

  client.on('auth_failure', (m) => {
    sess.status = 'auth_failure';
    sess.lastError = String(m);
    console.error(`[shop ${shopId}] auth_failure`, m);
  });

  client.initialize().catch((err) => {
    sess.status = 'error';
    sess.lastError = err && err.message ? err.message : String(err);
    console.error(`[shop ${shopId}] initialize failed:`, sess.lastError);
  });
  sess.client = client;
  sessions.set(shopId, sess);
  return sess;
}

app.post('/shops/:id/connect', auth, (req, res) => {
  const s = getOrCreate(Number(req.params.id));
  res.json({ status: s.status });
});

app.get('/shops/:id/status', auth, (req, res) => {
  const s = sessions.get(Number(req.params.id));
  if (!s) return res.json({ status: 'disconnected' });
  res.json({ status: s.status, me: s.me, error: s.lastError || null });
});

app.get('/shops/:id/qr', auth, (req, res) => {
  const s = sessions.get(Number(req.params.id));
  if (!s) return res.json({ qr: null, status: 'disconnected' });
  res.json({ qr: s.qr, status: s.status });
});

app.post('/shops/:id/send', auth, async (req, res) => {
  const s = sessions.get(Number(req.params.id));
  if (!s || !s.client || s.status !== 'ready') return res.status(400).json({ error: 'not ready' });
  try {
    const { to, text } = req.body;
    const chatId = to.includes('@') ? to : `${to.replace(/[^0-9]/g, '')}@c.us`;
    const r = await s.client.sendMessage(chatId, text);
    res.json({ ok: true, id: r.id?._serialized });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/shops/:id/logout', auth, async (req, res) => {
  const id = Number(req.params.id);
  const s = sessions.get(id);
  if (!s) return res.json({ ok: true });
  try { await s.client.logout(); } catch {}
  try { await s.client.destroy(); } catch {}
  sessions.delete(id);
  res.json({ ok: true });
});

app.get('/health', (req, res) => res.json({ ok: true, shops: sessions.size }));

const SESSIONS_DIR = './.wa-sessions';
function autoRestoreSessions() {
  if (!fs.existsSync(SESSIONS_DIR)) return;
  let entries = [];
  try { entries = fs.readdirSync(SESSIONS_DIR); } catch { return; }
  for (const name of entries) {
    // LocalAuth создаёт каталоги вида session-shop_<id>
    const m = name.match(/^session-shop_(\d+)$/);
    if (!m) continue;
    const id = Number(m[1]);
    console.log(`[WA bridge] auto-restoring shop ${id}`);
    try { getOrCreate(id); } catch (e) { console.error(`auto-restore shop ${id} failed:`, e.message); }
  }
}

app.listen(PORT, () => {
  console.log(`[WA bridge] listening on :${PORT}`);
  // Восстанавливаем сохранённые сессии — иначе после рестарта моста никто не слушает входящие.
  autoRestoreSessions();
});
