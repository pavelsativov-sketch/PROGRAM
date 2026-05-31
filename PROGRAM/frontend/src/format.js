/**
 * Денежный форматтер с уважением к валюте магазина (Shop.currency).
 * RUB → ₽, KZT → ₸, USD → $, EUR → €. Если код неизвестен — оставляем как есть.
 */
const SYMBOLS = { RUB: '₽', KZT: '₸', USD: '$', EUR: '€', UAH: '₴', BYN: 'Br', GBP: '£' };

export function currencySymbol(code) {
  if (!code) return '';
  return SYMBOLS[code.toUpperCase()] || code.toUpperCase();
}

export function formatMoney(amount, currency = 'RUB', { withFraction = false } = {}) {
  const n = Number(amount || 0);
  const sym = currencySymbol(currency);
  const fixed = withFraction ? n.toFixed(2) : Math.round(n).toLocaleString('ru-RU');
  return `${fixed} ${sym}`.trim();
}

export function formatTimeAgo(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'только что';
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} дн назад`;
  return d.toLocaleDateString();
}

export function shortDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString([], { day: '2-digit', month: '2-digit' });
}

export function timeOfDay(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function initials(name) {
  if (!name) return '?';
  const parts = String(name).trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return String(name).slice(0, 2).toUpperCase();
}
