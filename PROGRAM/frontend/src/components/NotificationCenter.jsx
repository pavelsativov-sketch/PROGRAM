import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { IconBell, IconTrash } from '../icons.jsx';

const TYPE_META = {
  handoff:       { label: 'Нужен менеджер', dot: 'var(--terracotta)' },
  bot_down:      { label: 'Бот офлайн',      dot: '#d64545' },
  bot_disabled:  { label: 'Бот выключен',    dot: '#d64545' },
  bot_idle:      { label: 'Тишина в канале', dot: '#e0a106' },
  ai_error:      { label: 'Сбой AI',         dot: '#d64545' },
  new_order:     { label: 'Новый счёт',      dot: 'var(--botanic)' },
  order_paid:    { label: 'Оплата',          dot: 'var(--botanic)' },
  reminder:      { label: 'Напоминание',     dot: '#7a6cc4' },
  followup:      { label: 'Дожим диалога',   dot: '#7a6cc4' },
  daily_summary: { label: 'Сводка дня',      dot: 'var(--botanic)' },
};

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'только что';
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  return `${Math.floor(diff / 86400)} дн назад`;
}

export default function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const seenRef = useRef(null);
  const boxRef = useRef(null);
  const nav = useNavigate();

  const refresh = async () => {
    try {
      const data = await api.notifications.list({ limit: 30 });
      setItems(data.items || []);
      setUnread(data.unread_count || 0);
      // Браузер-пуш про самое свежее непрочитанное (после первого опроса).
      const top = (data.items || [])[0];
      if (top && seenRef.current !== null && top.id > seenRef.current && !top.is_read) {
        maybeNotify(top);
      }
      if (top) seenRef.current = Math.max(seenRef.current || 0, top.id);
    } catch {}
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const onDoc = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const onItemClick = async (n) => {
    try { if (!n.is_read) await api.notifications.markRead(n.id); } catch {}
    setOpen(false);
    await refresh();
    if (n.link) nav(n.link);
  };

  const markAll = async () => { try { await api.notifications.markAllRead(); } catch {} refresh(); };
  const removeOne = async (e, id) => { e.stopPropagation(); try { await api.notifications.remove(id); } catch {} refresh(); };

  return (
    <div className="notif" ref={boxRef}>
      <button className="notif-bell" onClick={() => setOpen(o => !o)} aria-label="Уведомления">
        <IconBell size={19} />
        {unread > 0 && <span className="notif-count">{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && (
        <div className="notif-panel">
          <div className="notif-head">
            <b>Уведомления</b>
            {unread > 0 && <button className="notif-link" onClick={markAll}>Прочитать все</button>}
          </div>
          <div className="notif-list">
            {items.length === 0 && <div className="notif-empty">Пока нет уведомлений 🌿</div>}
            {items.map(n => {
              const meta = TYPE_META[n.type] || { label: n.type, dot: 'var(--botanic)' };
              return (
                <div key={n.id} className={`notif-item ${n.is_read ? '' : 'unread'}`} onClick={() => onItemClick(n)}>
                  <span className="notif-dot" style={{ background: meta.dot }} />
                  <div className="notif-body">
                    <div className="notif-row">
                      <span className="notif-type">{meta.label}</span>
                      <span className="notif-time">{timeAgo(n.created_at)}</span>
                    </div>
                    <div className="notif-title">{n.title}</div>
                    {n.body && <div className="notif-text">{n.body}</div>}
                  </div>
                  <button className="notif-del" onClick={(e) => removeOne(e, n.id)} aria-label="Удалить">
                    <IconTrash size={14} />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

async function maybeNotify(n) {
  if (typeof Notification === 'undefined') return;
  if (Notification.permission === 'denied') return;
  if (Notification.permission === 'default') {
    const r = await Notification.requestPermission();
    if (r !== 'granted') return;
  }
  try {
    const note = new Notification(n.title, { body: (n.body || '').slice(0, 140), tag: `notif-${n.id}`, icon: '/favicon.svg' });
    note.onclick = () => { window.focus(); if (n.link) window.location.href = n.link; note.close(); };
  } catch {}
}
