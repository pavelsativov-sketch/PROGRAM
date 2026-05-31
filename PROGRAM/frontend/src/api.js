import { authStore } from './auth';

const base = '';

async function req(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  // Аутентификация — только через httpOnly cookie. credentials:'include' обязательно.
  const res = await fetch(base + path, { credentials: 'include', ...opts, headers });
  if (res.status === 401) {
    authStore.clear();
    if (location.pathname !== '/login' && location.pathname !== '/signup') location.href = '/login';
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || j.error || msg; } catch {}
    throw new Error(msg);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

async function upload(path, file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(base + path, { method: 'POST', credentials: 'include', body: fd });
  if (res.status === 401) {
    authStore.clear();
    if (location.pathname !== '/login' && location.pathname !== '/signup') location.href = '/login';
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || j.error || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  auth: {
    signup: (d) => req('/api/auth/signup', { method: 'POST', body: JSON.stringify(d) }),
    login: (d) => req('/api/auth/login', { method: 'POST', body: JSON.stringify(d) }),
    logout: () => req('/api/auth/logout', { method: 'POST' }),
    me: () => req('/api/auth/me'),
    updateMe: (d) => req('/api/auth/me', { method: 'PUT', body: JSON.stringify(d) }),
  },
  flows: {
    list: () => req('/api/flows'),
    get: (id) => req(`/api/flows/${id}`),
    create: (d) => req('/api/flows', { method: 'POST', body: JSON.stringify(d) }),
    update: (id, d) => req(`/api/flows/${id}`, { method: 'PUT', body: JSON.stringify(d) }),
    remove: (id) => req(`/api/flows/${id}`, { method: 'DELETE' }),
    activate: (id) => req(`/api/flows/${id}/activate`, { method: 'POST' }),
    seedAgent: () => req('/api/flows/seed-agent', { method: 'POST' }),
  },
  orders: {
    list: () => req('/api/orders'),
    get: (id) => req(`/api/orders/${id}`),
    setStatus: (id, status) => req(`/api/orders/${id}/status?status=${status}`, { method: 'POST' }),
    products: () => req('/api/orders/products/all'),
    createProduct: (d) => req('/api/orders/products', { method: 'POST', body: JSON.stringify(d) }),
    updateProduct: (id, d) => req(`/api/orders/products/${id}`, { method: 'PUT', body: JSON.stringify(d) }),
    deleteProduct: (id) => req(`/api/orders/products/${id}`, { method: 'DELETE' }),
    uploadProductImage: (file) => upload('/api/orders/products/upload', file),
  },
  conversations: {
    list: (status) => req('/api/conversations' + (status ? `?status=${encodeURIComponent(status)}` : '')),
    get: (id) => req(`/api/conversations/${id}`),
    sim: (d) => req('/api/conversations/sim', { method: 'POST', body: JSON.stringify(d) }),
    takeover: (id) => req(`/api/conversations/${id}/takeover`, { method: 'POST' }),
    resume: (id) => req(`/api/conversations/${id}/resume`, { method: 'POST' }),
    reply: (id, text) => req(`/api/conversations/${id}/reply`, { method: 'POST', body: JSON.stringify({ text }) }),
  },
  wa: {
    status: () => req('/api/channels/whatsapp/status'),
    connect: () => req('/api/channels/whatsapp/connect', { method: 'POST' }),
    qr: () => req('/api/channels/whatsapp/qr'),
    logout: () => req('/api/channels/whatsapp/logout', { method: 'POST' }),
  },
  ig: {
    status: () => req('/api/channels/instagram/status'),
    login: (d) => req('/api/channels/instagram/login', { method: 'POST', body: JSON.stringify(d) }),
    logout: () => req('/api/channels/instagram/logout', { method: 'POST' }),
    setProxy: (proxy) => req('/api/channels/instagram/proxy', { method: 'POST', body: JSON.stringify({ proxy }) }),
  },
  customers: {
    list: (q) => req('/api/customers' + (q ? `?q=${encodeURIComponent(q)}` : '')),
    get: (id) => req(`/api/customers/${id}`),
    update: (id, d) => req(`/api/customers/${id}`, { method: 'PUT', body: JSON.stringify(d) }),
  },
  analytics: {
    summary: () => req('/api/analytics/summary'),
    report: (days) => req('/api/analytics/report' + (days ? `?days=${days}` : '')),
  },
  notifications: {
    list: (opts = {}) => {
      const p = new URLSearchParams();
      if (opts.unread) p.set('unread', 'true');
      if (opts.limit) p.set('limit', String(opts.limit));
      const qs = p.toString();
      return req('/api/notifications' + (qs ? `?${qs}` : ''));
    },
    unreadCount: () => req('/api/notifications/unread-count'),
    markRead: (id) => req(`/api/notifications/${id}/read`, { method: 'POST' }),
    markAllRead: () => req('/api/notifications/read-all', { method: 'POST' }),
    remove: (id) => req(`/api/notifications/${id}`, { method: 'DELETE' }),
    telegramTest: (d) => req('/api/notifications/telegram/test', { method: 'POST', body: JSON.stringify(d || {}) }),
    telegramDiscoverChat: (d) => req('/api/notifications/telegram/discover-chat', { method: 'POST', body: JSON.stringify(d || {}) }),
  },
};
