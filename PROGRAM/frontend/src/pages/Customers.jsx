import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { formatMoney, initials, formatTimeAgo } from '../format';
import {
  IconUsers, IconWhatsapp, IconInstagram, IconLab, IconChat,
  IconNote, IconClose, IconChevron, IconBag, IconCalendar,
} from '../icons.jsx';

const CHANNEL_ICON = {
  whatsapp: IconWhatsapp,
  instagram: IconInstagram,
  sim: IconLab,
};
const STATUS_LABELS = {
  active: 'AI ведёт',
  handoff: 'менеджер',
  pending_payment: 'ждёт оплаты',
  payment_review: 'проверка',
  paid: 'оплачено',
  closed: 'закрыт',
};

const SUGGESTED_TAGS = ['VIP', 'Постоянный', 'Корпоратив', 'Сложный', 'Подписка'];

export default function Customers() {
  const { id } = useParams();
  const nav = useNavigate();
  const [list, setList] = useState([]);
  const [q, setQ] = useState('');
  const [me, setMe] = useState(null);

  const load = (query) => api.customers.list(query).then(setList).catch(() => {});
  useEffect(() => {
    api.auth.me().then(setMe).catch(() => {});
  }, []);
  useEffect(() => {
    const t = setTimeout(() => load(q), 200);
    return () => clearTimeout(t);
  }, [q]);

  if (id) return <CustomerDetail id={id} currency={me?.currency || 'RUB'} onBack={() => nav('/customers')} />;

  const ccy = me?.currency || 'RUB';

  return (
    <div className="fade-in">
      <div className="header">
        <div>
          <h2 style={{fontStyle:'italic'}}>Клиенты</h2>
          <div className="muted">CRM: история заказов, теги, заметки.</div>
        </div>
        <div className="row">
          <input
            placeholder="Поиск по имени, телефону, нику…"
            value={q}
            onChange={e => setQ(e.target.value)}
            style={{minWidth:280}}
          />
        </div>
      </div>

      <div className="card" style={{padding: 0, overflow:'hidden'}}>
        {list.length === 0 ? (
          <div className="empty-state" style={{padding:'40px 20px'}}>
            <IconUsers size={28} />
            <div style={{marginTop:8}}>{q ? 'Не нашли никого по запросу.' : 'Клиенты появятся, как только напишут вам в WhatsApp или Instagram.'}</div>
          </div>
        ) : list.map(c => {
          const Icon = CHANNEL_ICON[c.channel] || IconChat;
          const avatarTone = c.id % 3 === 0 ? '' : (c.id % 3 === 1 ? 'terracotta' : 'ochre');
          return (
            <div key={c.id} className="customer-row" onClick={() => nav(`/customers/${c.id}`)}>
              <div style={{display:'flex', gap:12, alignItems:'center', minWidth:0}}>
                <div className={`conv-avatar ${avatarTone}`}>{initials(c.name || c.external_id)}</div>
                <div style={{minWidth:0}}>
                  <div className="customer-name">{c.name || c.external_id || `Клиент #${c.id}`}</div>
                  <div className="customer-meta">
                    <Icon size={12} style={{verticalAlign:'middle', marginRight:4}} />
                    {c.external_id || '—'}
                    {c.last_order_at && <> · последний заказ {formatTimeAgo(c.last_order_at)}</>}
                  </div>
                  {(c.tags || []).length > 0 && (
                    <div className="row" style={{marginTop:6, gap:4}}>
                      {(c.tags || []).slice(0, 3).map(t => <span key={t} className="tag">{t}</span>)}
                    </div>
                  )}
                </div>
              </div>
              <div style={{textAlign:'right'}}>
                <div className="muted" style={{fontSize:11, textTransform:'uppercase', letterSpacing:'0.08em', fontWeight:600}}>заказов</div>
                <div className="mono" style={{fontWeight:600, fontSize:16}}>{c.orders}</div>
              </div>
              <div style={{textAlign:'right'}}>
                <div className="muted" style={{fontSize:11, textTransform:'uppercase', letterSpacing:'0.08em', fontWeight:600}}>LTV</div>
                <div className="mono" style={{fontWeight:600, fontSize:16}}>{formatMoney(c.ltv, ccy)}</div>
              </div>
              <IconChevron size={16} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CustomerDetail({ id, currency, onBack }) {
  const [c, setC] = useState(null);
  const [draftTag, setDraftTag] = useState('');
  const [savedNotice, setSavedNotice] = useState('');
  const nav = useNavigate();

  const load = () => api.customers.get(id).then(setC).catch(() => setC(null));
  useEffect(() => { load(); }, [id]);

  if (!c) return <div className="card empty-state"><span className="pulse-dot" /> загрузка карточки…</div>;

  const Icon = CHANNEL_ICON[c.channel] || IconChat;

  const flash = (msg) => {
    setSavedNotice(msg);
    setTimeout(() => setSavedNotice(''), 1800);
  };

  const addTag = async (tag) => {
    const t = (tag || draftTag || '').trim();
    if (!t) return;
    if ((c.tags || []).some(x => x.toLowerCase() === t.toLowerCase())) {
      setDraftTag('');
      return;
    }
    const next = [...(c.tags || []), t];
    const r = await api.customers.update(id, { tags: next });
    setC({ ...c, tags: r.tags });
    setDraftTag('');
    flash('тег добавлен');
  };
  const removeTag = async (tag) => {
    const next = (c.tags || []).filter(x => x !== tag);
    const r = await api.customers.update(id, { tags: next });
    setC({ ...c, tags: r.tags });
  };
  const saveNotes = async (notes) => {
    const r = await api.customers.update(id, { notes });
    setC({ ...c, notes: r.notes });
    flash('заметка сохранена');
  };
  const saveDates = async (important_dates) => {
    const r = await api.customers.update(id, { important_dates });
    setC({ ...c, important_dates: r.important_dates });
    flash('даты сохранены');
  };

  return (
    <div className="fade-in">
      <div className="header">
        <div className="row" style={{alignItems:'center'}}>
          <button className="ghost small" onClick={onBack}>← Все клиенты</button>
        </div>
      </div>

      <div className="card">
        <div style={{display:'flex', gap:18, alignItems:'flex-start'}}>
          <div className="conv-avatar" style={{width:56, height:56, fontSize:18}}>{initials(c.name || c.external_id)}</div>
          <div style={{flex:1, minWidth:0}}>
            <div style={{display:'flex', alignItems:'baseline', gap:10, flexWrap:'wrap'}}>
              <h2 style={{fontStyle:'italic'}}>{c.name || c.external_id || `Клиент #${c.id}`}</h2>
              <span className="muted"><Icon size={14} style={{verticalAlign:'middle', marginRight:4}} />{c.channel || '—'} · {c.external_id || '—'}</span>
            </div>
            <div className="muted" style={{marginTop:4, fontSize:13}}>
              Клиент с {c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}
            </div>

            <div className="row" style={{marginTop:14, gap:6}}>
              {(c.tags || []).map(t => (
                <span key={t} className="tag removable">
                  {t}
                  <button onClick={() => removeTag(t)} title="удалить тег">×</button>
                </span>
              ))}
              <div className="row" style={{gap:6}}>
                <input
                  style={{width:160}}
                  placeholder="новый тег"
                  value={draftTag}
                  onChange={e => setDraftTag(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } }}
                />
                <button className="small secondary" onClick={() => addTag()}>+</button>
              </div>
            </div>
            <div className="row" style={{gap:6, marginTop:6}}>
              {SUGGESTED_TAGS
                .filter(t => !(c.tags || []).map(x => x.toLowerCase()).includes(t.toLowerCase()))
                .map(t => (
                  <button key={t} className="chip" onClick={() => addTag(t)} style={{padding:'3px 10px', fontSize:12}}>+ {t}</button>
                ))}
            </div>
          </div>
        </div>

        <div className="grid-3" style={{marginTop:18}}>
          <Stat label="Всего заказов" value={c.stats.orders_count} />
          <Stat label="Оплачено" value={c.stats.paid_orders} />
          <Stat label="LTV" value={formatMoney(c.stats.ltv, currency)} mono />
        </div>
      </div>

      <div className="dash-grid">
        <div className="card">
          <div className="header" style={{marginBottom:10}}>
            <h3 className="serif" style={{fontStyle:'italic'}}>История заказов</h3>
            <span className="muted">{c.orders.length}</span>
          </div>
          {c.orders.length === 0 ? (
            <div className="empty-state" style={{padding:'24px 8px'}}>
              <IconBag size={22} /><div style={{marginTop:6}}>Пока ни одного заказа.</div>
            </div>
          ) : c.orders.map(o => (
            <div key={o.id} className="dash-list-item">
              <div className="left" style={{minWidth:0}}>
                <span className={`badge ${o.status}`}>{o.status}</span>
                <div style={{minWidth:0}}>
                  <div className="name">#{o.id} · {(o.items || []).map(i => i.name).filter(Boolean).slice(0,2).join(', ') || '—'}</div>
                  <div className="sub">{o.created_at ? new Date(o.created_at).toLocaleString() : ''}</div>
                </div>
              </div>
              <span className="mono" style={{fontWeight:600}}>{formatMoney(o.total, currency)}</span>
            </div>
          ))}
        </div>

        <div>
          <div className="card">
            <div className="header" style={{marginBottom:10}}>
              <h3 className="serif" style={{fontStyle:'italic'}}><IconNote size={18} style={{verticalAlign:'middle', marginRight:6}} />Заметки менеджера</h3>
              {savedNotice && <span className="muted" style={{fontSize:12, color:'var(--ok)'}}>✓ {savedNotice}</span>}
            </div>
            <NotesEditor initial={c.notes || ''} onSave={saveNotes} />
            <div className="muted" style={{fontSize:12, marginTop:8}}>
              Например: «любит белые пионы», «дочери 5 лет — день рождения 12 апреля», «всегда платит на следующий день».
            </div>
          </div>

          <div className="card">
            <div className="header" style={{marginBottom:10}}>
              <h3 className="serif" style={{fontStyle:'italic'}}><IconCalendar size={18} style={{verticalAlign:'middle', marginRight:6}} />Важные даты</h3>
            </div>
            <ImportantDates initial={c.important_dates || []} onSave={saveDates} />
            <div className="muted" style={{fontSize:12, marginTop:8}}>
              Дни рождения, годовщины. Менеджер получит напоминание за день — отличный повод предложить заказать снова.
            </div>
          </div>

          {c.conversations.length > 0 && (
            <div className="card">
              <h3 className="serif" style={{fontStyle:'italic', marginBottom:10}}>Диалоги</h3>
              {c.conversations.slice(0, 5).map(cv => (
                <div key={cv.id} className="dash-list-item" style={{cursor:'pointer'}} onClick={() => nav(`/conversations/${cv.id}`)}>
                  <div className="left">
                    <IconChat size={18} />
                    <div>
                      <div className="name">Диалог #{cv.id}</div>
                      <div className="sub">{cv.updated_at ? formatTimeAgo(cv.updated_at) : ''}</div>
                    </div>
                  </div>
                  <span className={`badge ${cv.status}`}>{STATUS_LABELS[cv.status] || cv.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, mono }) {
  return (
    <div className="kpi" style={{padding:'14px 16px'}}>
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${mono ? 'mono' : ''}`} style={{fontSize:24}}>{value ?? 0}</div>
    </div>
  );
}

function NotesEditor({ initial, onSave }) {
  const [val, setVal] = useState(initial);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setVal(initial); }, [initial]);
  const dirty = val !== initial;
  const save = async () => {
    setBusy(true);
    try { await onSave(val); } finally { setBusy(false); }
  };
  return (
    <div>
      <textarea
        rows={5}
        value={val}
        onChange={e => setVal(e.target.value)}
        placeholder="Что важно помнить о клиенте?"
      />
      <div className="row" style={{marginTop:8, justifyContent:'flex-end'}}>
        <button className="small" onClick={save} disabled={busy || !dirty}>
          {busy ? 'Сохранение…' : 'Сохранить заметку'}
        </button>
      </div>
    </div>
  );
}

const DATE_LABELS = ['День рождения', 'Годовщина', 'Другое'];

function ImportantDates({ initial, onSave }) {
  const [rows, setRows] = useState(() => (initial || []).map(normRow));
  const [busy, setBusy] = useState(false);
  useEffect(() => { setRows((initial || []).map(normRow)); }, [initial]);

  const dirty = JSON.stringify(rows) !== JSON.stringify((initial || []).map(normRow));

  const update = (i, patch) => setRows(rs => rs.map((r, idx) => idx === i ? { ...r, ...patch } : r));
  const add = () => setRows(rs => [...rs, { label: 'День рождения', date: '', recurring: true }]);
  const remove = (i) => setRows(rs => rs.filter((_, idx) => idx !== i));
  const save = async () => {
    setBusy(true);
    try { await onSave(rows.filter(r => r.date)); } finally { setBusy(false); }
  };

  return (
    <div>
      {rows.length === 0 && <div className="muted" style={{fontSize:13, marginBottom:8}}>Дат пока нет.</div>}
      {rows.map((r, i) => (
        <div key={i} className="row" style={{gap:8, marginBottom:8, flexWrap:'wrap', alignItems:'center'}}>
          <select value={DATE_LABELS.includes(r.label) ? r.label : 'Другое'}
                  onChange={e => update(i, { label: e.target.value })} style={{width:150}}>
            {DATE_LABELS.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
          <input type="date" value={r.date} onChange={e => update(i, { date: e.target.value })} style={{width:160}} />
          <label className="row" style={{gap:5, margin:0, textTransform:'none', fontSize:12, color:'var(--ink-2)', letterSpacing:0, fontWeight:500}}>
            <input type="checkbox" style={{width:'auto', margin:0}} checked={!!r.recurring} onChange={e => update(i, { recurring: e.target.checked })} />
            ежегодно
          </label>
          <button className="ghost small" onClick={() => remove(i)} title="удалить"><IconClose size={14} /></button>
        </div>
      ))}
      <div className="row" style={{marginTop:6, justifyContent:'space-between'}}>
        <button className="secondary small" onClick={add}>+ Добавить дату</button>
        <button className="small" onClick={save} disabled={busy || !dirty}>
          {busy ? 'Сохранение…' : 'Сохранить'}
        </button>
      </div>
    </div>
  );
}

function normRow(r) {
  return { label: r.label || 'Другое', date: (r.date || '').slice(0, 10), recurring: r.recurring !== false };
}
