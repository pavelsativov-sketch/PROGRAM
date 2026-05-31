import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { formatMoney, currencySymbol, timeOfDay } from '../format';
import { IconPrinter, IconClose, IconBouquet } from '../icons.jsx';

const COLUMNS = [
  { key: 'new',             label: 'Новые' },
  { key: 'pending_payment', label: 'Ждут оплаты' },
  { key: 'payment_review',  label: 'Проверка оплаты' },
  { key: 'paid',            label: 'Оплачены · собирают' },
  { key: 'delivered',       label: 'Доставлены' },
  { key: 'cancelled',       label: 'Отменены' },
];

const STATUS_LABELS = Object.fromEntries(COLUMNS.map(c => [c.key, c.label]));

export default function Orders() {
  const [orders, setOrders] = useState([]);
  const [selected, setSelected] = useState(null);
  const [me, setMe] = useState(null);
  const [view, setView] = useState('kanban');  // kanban | table
  const [draggingId, setDraggingId] = useState(null);
  const [dropCol, setDropCol] = useState(null);

  const load = () => api.orders.list().then(setOrders).catch(() => {});
  useEffect(() => {
    api.auth.me().then(setMe).catch(() => {});
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, []);

  const ccy = me?.currency || 'RUB';

  const grouped = useMemo(() => {
    const g = Object.fromEntries(COLUMNS.map(c => [c.key, []]));
    for (const o of orders) {
      const key = g[o.status] ? o.status : 'new';
      g[key].push(o);
    }
    return g;
  }, [orders]);

  const changeStatus = async (id, status) => {
    await api.orders.setStatus(id, status);
    setOrders(prev => prev.map(o => o.id === id ? { ...o, status } : o));
    if (selected?.id === id) setSelected({ ...selected, status });
  };

  const onDragStart = (e, id) => {
    setDraggingId(id);
    e.dataTransfer.effectAllowed = 'move';
    try { e.dataTransfer.setData('text/plain', String(id)); } catch {}
  };
  const onDragEnd = () => { setDraggingId(null); setDropCol(null); };
  const onDragOver = (e, col) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dropCol !== col) setDropCol(col);
  };
  const onDrop = async (e, col) => {
    e.preventDefault();
    setDropCol(null);
    const id = Number(draggingId || e.dataTransfer.getData('text/plain'));
    setDraggingId(null);
    if (!id) return;
    const o = orders.find(x => x.id === id);
    if (!o || o.status === col) return;
    await changeStatus(id, col);
  };

  const printInvoice = (order) => {
    const html = renderInvoiceHTML(order, me);
    const w = window.open('', '_blank', 'width=820,height=900');
    if (!w) return;
    w.document.open();
    w.document.write(html);
    w.document.close();
    setTimeout(() => { try { w.focus(); w.print(); } catch {} }, 300);
  };

  return (
    <div className="fade-in">
      <div className="header">
        <div>
          <h2 style={{fontStyle:'italic'}}>Заказы</h2>
          <div className="muted">Перетаскивайте карточки между этапами — статус меняется на лету.</div>
        </div>
        <div className="row">
          <button className={`chip ${view === 'kanban' ? 'on' : ''}`} onClick={() => setView('kanban')}>Канбан</button>
          <button className={`chip ${view === 'table' ? 'on' : ''}`} onClick={() => setView('table')}>Список</button>
        </div>
      </div>

      {view === 'kanban' && (
        <div className="kanban">
          {COLUMNS.map(col => {
            const list = grouped[col.key] || [];
            const sum = list.reduce((s, o) => s + (Number(o.total) || 0), 0);
            const dropping = dropCol === col.key;
            return (
              <div
                key={col.key}
                className={`kanban-col ${dropping ? 'drop-target' : ''}`}
                onDragOver={e => onDragOver(e, col.key)}
                onDragLeave={() => dropCol === col.key && setDropCol(null)}
                onDrop={e => onDrop(e, col.key)}
              >
                <div className="kanban-col-head">
                  <span className="kanban-col-title">{col.label}</span>
                  <span className="kanban-col-count">{list.length}</span>
                </div>
                <div className="muted" style={{fontSize:11, marginBottom:8, fontFamily:'var(--mono)'}}>
                  Σ {formatMoney(sum, ccy)}
                </div>
                {list.length === 0 && (
                  <div className="muted" style={{textAlign:'center', padding:'14px 4px', fontStyle:'italic', fontFamily:'var(--serif)', fontSize:13}}>
                    пусто
                  </div>
                )}
                {list.map(o => (
                  <div
                    key={o.id}
                    className={`kanban-card ${draggingId === o.id ? 'dragging' : ''}`}
                    draggable
                    onDragStart={e => onDragStart(e, o.id)}
                    onDragEnd={onDragEnd}
                    onClick={() => setSelected(o)}
                  >
                    {col.key === 'paid' && o.details?.delivery_date && <span className="ribbon">в работу</span>}
                    <div className="order-no">#{o.id} · {timeOfDay(o.created_at)}</div>
                    <div className="name">{o.details?.name || 'Без имени'}</div>
                    <div className="items">
                      {(o.items || []).map(i => `${i.name || '?'}×${i.qty || 1}`).join(', ') || '—'}
                    </div>
                    <div className="total">{formatMoney(o.total, ccy)}</div>
                    {o.details?.delivery_date && (
                      <div className="deliver">→ {o.details.delivery_date}</div>
                    )}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}

      {view === 'table' && (
        <div className="card">
          <table>
            <thead>
              <tr><th>№</th><th>Клиент</th><th>Товары</th><th>Сумма</th><th>Статус</th><th>Дата</th><th></th></tr>
            </thead>
            <tbody>
              {orders.map(o => (
                <tr key={o.id}>
                  <td className="mono">#{o.id}</td>
                  <td>
                    <div style={{fontWeight:600, fontFamily:'var(--serif)'}}>{o.details?.name || '—'}</div>
                    <div className="muted">{o.details?.phone}</div>
                  </td>
                  <td>{(o.items || []).map(i => `${i.name}×${i.qty||1}`).join(', ')}</td>
                  <td className="mono" style={{fontWeight:600}}>{formatMoney(o.total, ccy)}</td>
                  <td><span className={`badge ${o.status}`}>{STATUS_LABELS[o.status] || o.status}</span></td>
                  <td>{new Date(o.created_at).toLocaleString()}</td>
                  <td>
                    <div className="row">
                      <button className="ghost small" onClick={() => setSelected(o)}>Детали</button>
                      <button className="ghost small" onClick={() => printInvoice(o)} title="Печать накладной">
                        <IconPrinter size={14} />
                      </button>
                      {o.payment_link && <a className="btn small" href={o.payment_link} target="_blank" rel="noreferrer">Счёт</a>}
                    </div>
                  </td>
                </tr>
              ))}
              {orders.length === 0 && (
                <tr><td colSpan={7}><div className="empty-state"><IconBouquet size={26} /><div style={{marginTop:6}}>Заказов пока нет.</div></div></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <OrderDrawer
          order={selected}
          currency={ccy}
          onClose={() => setSelected(null)}
          onChangeStatus={(s) => changeStatus(selected.id, s)}
          onPrint={() => printInvoice(selected)}
        />
      )}
    </div>
  );
}

function OrderDrawer({ order, currency, onClose, onChangeStatus, onPrint }) {
  return (
    <div className="card fade-in" style={{marginTop:18}}>
      <div className="header">
        <div>
          <h3 className="serif" style={{fontStyle:'italic'}}>Заказ #{order.id}</h3>
          <div className="muted">{new Date(order.created_at).toLocaleString()}</div>
        </div>
        <div className="row">
          <button className="ghost small" onClick={onPrint}><IconPrinter size={14} /> Накладная</button>
          {order.payment_link && <a className="btn small secondary" href={order.payment_link} target="_blank" rel="noreferrer">Счёт</a>}
          <button className="ghost small" onClick={onClose}><IconClose size={14} /></button>
        </div>
      </div>
      <div className="grid-2">
        <div>
          <label>Клиент</label>
          <div style={{fontFamily:'var(--serif)', fontSize:18, fontWeight:600}}>{order.details?.name || '—'}</div>
          <div className="muted" style={{marginTop:4}}>
            {order.details?.phone || '—'}<br />
            {order.details?.address || '—'}<br />
            Доставка: {order.details?.delivery_date || '—'}
          </div>
          {order.details?.wishes && (
            <div className="note-box" style={{marginTop:10}}>
              «{order.details.wishes}»
            </div>
          )}
        </div>
        <div>
          <label>Позиции</label>
          {(order.items || []).map((i, idx) => (
            <div key={idx} style={{display:'flex', justifyContent:'space-between', padding:'4px 0', borderBottom:'1px dashed var(--line)'}}>
              <span>{i.name} × {i.qty || 1}</span>
              <span className="mono">{formatMoney((Number(i.price) || 0) * (Number(i.qty) || 1), currency)}</span>
            </div>
          ))}
          <div style={{marginTop:10, display:'flex', justifyContent:'space-between', fontWeight:700, fontSize:16, fontFamily:'var(--mono)'}}>
            <span>Итого</span>
            <span>{formatMoney(order.total, currency)}</span>
          </div>
        </div>
      </div>
      <div className="divider" />
      <div className="row">
        <span className="muted" style={{marginRight:8, fontSize:12, letterSpacing:'0.08em', textTransform:'uppercase', fontWeight:600}}>Статус</span>
        {COLUMNS.map(c => (
          <button
            key={c.key}
            className={`small ${order.status === c.key ? '' : 'secondary'}`}
            onClick={() => onChangeStatus(c.key)}
          >
            {c.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Минимальный HTML-шаблон накладной — открывается в новом окне и сразу
 *  вызывается window.print(). Содержит всё, что нужно курьеру:
 *  адрес, время, состав, сумма, пожелания, телефон. */
function renderInvoiceHTML(order, shop) {
  const ccy = shop?.currency || 'RUB';
  const sym = currencySymbol(ccy);
  const items = (order.items || [])
    .map(i => `<tr>
        <td>${esc(i.name)}</td>
        <td style="text-align:center">${i.qty || 1}</td>
        <td style="text-align:right">${money(i.price, sym)}</td>
        <td style="text-align:right">${money((Number(i.price)||0) * (Number(i.qty)||1), sym)}</td>
      </tr>`).join('');
  const total = money(order.total, sym);
  const wishes = order.details?.wishes
    ? `<div class="card" style="margin-top:18px"><b>Открытка / пожелания:</b><br>«${esc(order.details.wishes)}»</div>`
    : '';
  return `<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8" />
<title>Накладная #${order.id}</title>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@500;600&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet" />
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Manrope', sans-serif; color: #2b1f1a; padding: 28px; max-width: 760px; margin: 0 auto; background: #fbf7f1; }
  h1 { font-family: 'Fraunces', serif; font-style: italic; margin: 0; font-size: 28px; }
  .muted { color: #8a7868; }
  .card { border: 1px solid #e6dccc; padding: 14px 16px; border-radius: 10px; background: #fff; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 18px 0; }
  table { width: 100%; border-collapse: collapse; margin-top: 10px; }
  th { text-align: left; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: #8a7868; border-bottom: 1px solid #2b1f1a; padding: 8px 4px; }
  td { padding: 8px 4px; border-bottom: 1px dashed #e6dccc; }
  .total { display: flex; justify-content: space-between; padding-top: 12px; margin-top: 14px; border-top: 2px solid #2b1f1a; font-size: 18px; font-weight: 700; font-family: 'Fraunces', serif; }
  .footer { margin-top: 28px; font-size: 12px; color: #8a7868; text-align: center; }
  @media print { body { background: #fff; padding: 16px; } .no-print { display: none; } }
</style>
</head>
<body>
  <header style="display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:14px;border-bottom:1px solid #e6dccc;padding-bottom:10px;">
    <div>
      <h1>${esc(shop?.name || 'Floral')}</h1>
      <div class="muted">${esc(shop?.kaspi_phone || shop?.email || '')}</div>
    </div>
    <div style="text-align:right">
      <div class="muted" style="font-size:11px;letter-spacing:.1em;text-transform:uppercase">Накладная</div>
      <div style="font-family:'Fraunces',serif;font-size:24px">№ ${order.id}</div>
      <div class="muted" style="font-size:12px">${new Date(order.created_at).toLocaleString('ru-RU')}</div>
    </div>
  </header>

  <div class="grid">
    <div class="card">
      <div class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.08em">Получатель</div>
      <div style="font-family:'Fraunces',serif;font-size:18px;margin-top:4px">${esc(order.details?.name || '—')}</div>
      <div>${esc(order.details?.phone || '')}</div>
      <div>${esc(order.details?.address || '')}</div>
    </div>
    <div class="card">
      <div class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.08em">Доставка</div>
      <div style="font-family:'Fraunces',serif;font-size:18px;margin-top:4px">${esc(order.details?.delivery_date || '—')}</div>
      <div class="muted">${esc(order.details?.delivery_slot || '')}</div>
    </div>
  </div>

  <table>
    <thead><tr><th>Позиция</th><th style="text-align:center">Кол-во</th><th style="text-align:right">Цена</th><th style="text-align:right">Сумма</th></tr></thead>
    <tbody>${items || '<tr><td colspan="4" class="muted">—</td></tr>'}</tbody>
  </table>
  <div class="total"><span>К оплате</span><span>${total}</span></div>
  ${wishes}

  <div class="footer">
    Спасибо, что выбрали ${esc(shop?.name || 'наше ателье цветов')}. 🌿
  </div>

  <div class="no-print" style="text-align:center;margin-top:24px;">
    <button onclick="window.print()" style="background:#c97064;color:#fff;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;font-family:'Manrope',sans-serif;font-weight:600;font-size:14px">Печать</button>
  </div>
</body></html>`;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]
  ));
}
function money(n, sym) {
  const v = Math.round(Number(n || 0)).toLocaleString('ru-RU');
  return `${v} ${sym}`;
}
