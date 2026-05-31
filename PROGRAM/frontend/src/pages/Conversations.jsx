import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { initials } from '../format';
import { IconWhatsapp, IconInstagram, IconLab, IconChat, IconUsers } from '../icons.jsx';

const FILTERS = [
  { key: 'all',             label: 'Все' },
  { key: 'handoff',         label: 'Нужен менеджер' },
  { key: 'active',          label: 'Активные (AI)' },
  { key: 'pending_payment', label: 'Ждут оплаты' },
  { key: 'payment_review',  label: 'Проверка оплаты' },
  { key: 'closed',          label: 'Закрытые' },
];

const STATUS_LABELS = {
  active: 'AI ведёт диалог',
  handoff: 'Нужен менеджер',
  pending_payment: 'Ждёт оплаты',
  payment_review: 'Проверка оплаты',
  paid: 'Оплачен',
  closed: 'Закрыт',
};

const CHANNEL_ICONS = {
  whatsapp: IconWhatsapp,
  instagram: IconInstagram,
  sim: IconLab,
};
function ChannelIcon({ ch, size = 14 }) {
  const I = CHANNEL_ICONS[ch] || IconChat;
  return <I size={size} />;
}

function fmtTime(s) {
  if (!s) return '';
  const d = new Date(s);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return d.toLocaleDateString([], { day: '2-digit', month: '2-digit' });
}

function contactTitle(c) {
  const cu = c.customer || {};
  if (cu.name && cu.name !== 'Симулятор') return cu.name;
  if (cu.external_id) return cu.external_id;
  return `Диалог #${c.id}`;
}

export default function Conversations() {
  const [list, setList] = useState([]);
  const { id } = useParams();
  const [cur, setCur] = useState(null);
  const [search, setSearch] = useState('');
  const [params, setParams] = useSearchParams();
  const filter = params.get('filter') || 'all';
  const setFilter = (k) => setParams(k === 'all' ? {} : { filter: k }, { replace: true });

  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const nav = useNavigate();
  const endRef = useRef();

  const loadList = () => api.conversations.list(filter === 'all' ? undefined : filter)
    .then(setList).catch(e => setError(String(e.message || e)));
  useEffect(() => { loadList(); const t = setInterval(loadList, 5000); return () => clearInterval(t); }, [filter]);

  const loadCur = () => { if (id) api.conversations.get(id).then(setCur).catch(() => setCur(null)); else setCur(null); };
  useEffect(() => { loadCur(); }, [id]);
  useEffect(() => {
    if (!id) return;
    const t = setInterval(loadCur, 4000);
    return () => clearInterval(t);
  }, [id]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [cur?.messages?.length]);

  const counts = useMemo(() => {
    // Берём текущий список — для подсветки числа handoff в чипе. Точные счётчики все равно требуют отдельного эндпоинта.
    return { handoff: list.filter(c => c.status === 'handoff').length };
  }, [list]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return list;
    return list.filter(c => {
      const title = contactTitle(c).toLowerCase();
      const last = (c.last_message?.text || '').toLowerCase();
      return title.includes(q) || last.includes(q) || String(c.id).includes(q);
    });
  }, [list, search]);

  const sendReply = async () => {
    if (!cur || !reply.trim()) return;
    setBusy(true); setError('');
    try {
      await api.conversations.reply(cur.id, reply.trim());
      setReply('');
      await loadCur();
    } catch (e) { setError(String(e.message || e)); }
    finally { setBusy(false); }
  };

  const takeover = async () => {
    if (!cur) return;
    try { await api.conversations.takeover(cur.id); await loadCur(); }
    catch (e) { setError(String(e.message || e)); }
  };
  const resume = async () => {
    if (!cur) return;
    if (!confirm('Вернуть диалог под управление AI?')) return;
    try { await api.conversations.resume(cur.id); await loadCur(); }
    catch (e) { setError(String(e.message || e)); }
  };

  const onReplyKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendReply(); }
  };

  return (
    <div className="fade-in">
      <div className="header">
        <div>
          <h2 style={{margin:0, fontStyle:'italic'}}>Диалоги</h2>
          <div className="muted">Все чаты с клиентами в одном месте.</div>
        </div>
      </div>

      <div className="filter-chips">
        {FILTERS.map(f => (
          <button
            key={f.key}
            className={`chip ${filter === f.key ? 'on' : ''}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
            {f.key === 'handoff' && counts.handoff > 0 && (
              <span className="chip-badge">{counts.handoff}</span>
            )}
          </button>
        ))}
      </div>

      {error && <div className="card" style={{color:'#dc2626'}}>{error}</div>}

      <div className="conv-grid">
        <div className="card conv-list">
          <input
            className="conv-search"
            placeholder="🔍 Поиск по имени, номеру, тексту..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {filtered.map(c => {
            const last = c.last_message;
            const isMe = String(c.id) === id;
            const cu = c.customer || {};
            return (
              <div key={c.id}
                onClick={() => nav(`/conversations/${c.id}`)}
                className={`conv-item ${isMe ? 'on' : ''} ${c.status === 'handoff' ? 'urgent' : ''}`}>
                <div className="conv-item-row">
                  <div className={`conv-avatar ${c.id % 3 === 1 ? 'terracotta' : c.id % 3 === 2 ? 'ochre' : ''}`}>
                    {initials(cu.name || cu.external_id || `#${c.id}`)}
                  </div>
                  <div style={{flex:1, minWidth:0}}>
                    <div className="conv-item-top">
                      <span className="conv-name">
                        <ChannelIcon ch={cu.channel} size={11} /> {contactTitle(c)}
                      </span>
                      <span className="conv-time">{fmtTime(last?.created_at || c.updated_at)}</span>
                    </div>
                    <div className="conv-item-bot">
                      <span className="conv-preview">
                        {last?.role === 'user' ? '' : '· '}
                        {last?.text || <span className="muted">—</span>}
                      </span>
                      <span className={`badge ${c.status}`}>{STATUS_LABELS[c.status] || c.status}</span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
          {filtered.length === 0 && <div className="muted" style={{padding:14}}>Диалогов пока нет.</div>}
        </div>

        <div>
          {!cur && <div className="card muted">Выберите диалог слева.</div>}
          {cur && (
            <div className="card">
              <div className="header" style={{marginBottom:8}}>
                <div>
                  <h3 className="serif" style={{margin:0, fontStyle:'italic'}}>
                    {cur.customer?.name || cur.customer?.external_id || `Диалог #${cur.id}`}
                  </h3>
                  <div className="muted">
                    <ChannelIcon ch={cur.customer?.channel} size={12} /> {cur.customer?.channel || 'без канала'} · {cur.customer?.external_id || '—'}
                  </div>
                </div>
                <div className="row">
                  <span className={`badge ${cur.status}`}>{STATUS_LABELS[cur.status] || cur.status}</span>
                  {cur.customer?.id && (
                    <button className="ghost small" onClick={() => nav(`/customers/${cur.customer.id}`)}>
                      <IconUsers size={14} /> Карточка клиента
                    </button>
                  )}
                  {cur.status !== 'handoff'
                    ? <button className="small" onClick={takeover}>Взять диалог</button>
                    : <button className="small secondary" onClick={resume}>Вернуть AI</button>}
                </div>
              </div>
              <div className="chat">
                <div className="chat-msgs">
                  {cur.messages.map(m => (
                    <div key={m.id} className={`msg ${m.role}`}>
                      {m.meta?.manager && <div style={{fontSize:11, color:'var(--ochre)', marginBottom:2, fontWeight:600}}>· менеджер</div>}
                      {m.text}
                      {m.meta?.send_error && <div style={{fontSize:11, color:'var(--err)', marginTop:2}}>не доставлено</div>}
                    </div>
                  ))}
                  <div ref={endRef} />
                </div>
              </div>

              <div style={{marginTop:10, borderTop:'1px solid var(--line)', paddingTop:10}}>
                <div className="muted" style={{marginBottom:6}}>
                  {cur.status === 'handoff'
                    ? 'Вы отвечаете клиенту от лица магазина. AI отключён для этого диалога.'
                    : 'AI ведёт диалог. Если ответите — диалог автоматически перейдёт к менеджеру.'}
                </div>
                <div className="row">
                  <input
                    style={{flex:1}}
                    placeholder="Ваш ответ клиенту..."
                    value={reply}
                    onChange={e => setReply(e.target.value)}
                    onKeyDown={onReplyKey}
                    disabled={busy}
                  />
                  <button onClick={sendReply} disabled={busy || !reply.trim()}>
                    {busy ? 'Отправка...' : 'Ответить'}
                  </button>
                </div>
              </div>

              {cur.variables && Object.keys(cur.variables).filter(k => !k.startsWith('_')).length > 0 && (
                <div style={{marginTop:10}}>
                  <div className="muted">Собранные данные:</div>
                  <pre style={{background:'var(--paper-2)', padding:10, borderRadius:'var(--r-sm)', fontSize:12, fontFamily:'var(--mono)', color:'var(--ink-2)', border:'1px solid var(--line)'}}>
                    {JSON.stringify(
                      Object.fromEntries(Object.entries(cur.variables).filter(([k]) => !k.startsWith('_'))),
                      null, 2
                    )}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
