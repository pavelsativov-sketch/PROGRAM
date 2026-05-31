import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { formatMoney, currencySymbol, timeOfDay } from '../format';
import {
  IconBouquet, IconChat, IconBag, IconWhatsapp, IconInstagram,
  IconLab, IconChevron, IconSparkle,
} from '../icons.jsx';

const STATUS_LABELS = {
  new: 'новый',
  pending_payment: 'ждёт оплаты',
  payment_review: 'проверка оплаты',
  paid: 'оплачен',
  delivered: 'доставлен',
  cancelled: 'отменён',
};

const CHANNEL_META = {
  whatsapp: { label: 'WhatsApp', icon: IconWhatsapp },
  instagram: { label: 'Instagram', icon: IconInstagram },
  sim:       { label: 'Симулятор', icon: IconLab },
};

function greetingByHour(hour) {
  if (hour < 5)  return 'Доброй ночи';
  if (hour < 12) return 'Доброе утро';
  if (hour < 18) return 'Добрый день';
  return 'Добрый вечер';
}

function todayLabel(now) {
  const months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
  return `${now.getDate()} ${months[now.getMonth()]}, ${['воскресенье','понедельник','вторник','среда','четверг','пятница','суббота'][now.getDay()]}`;
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [me, setMe] = useState(null);
  const [error, setError] = useState('');
  const nav = useNavigate();

  const load = () => api.analytics.summary().then(setData).catch(e => setError(String(e.message || e)));
  useEffect(() => {
    api.auth.me().then(setMe).catch(() => {});
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  if (error) return <div className="card"><div className="err">{error}</div></div>;
  if (!data) {
    return (
      <div className="card empty-state">
        <span className="pulse-dot" /> загружаем сегодняшний день…
      </div>
    );
  }

  const now = data.now ? new Date(data.now) : new Date();
  const ccy = data.currency || me?.currency || 'RUB';
  const conv = data.conversations || {};
  const today = data.today || {};
  const hours = today.hours || [];
  const maxHour = Math.max(1, ...hours.map(h => h.count));

  // Берём «значимые» часы для оси: 8-22.
  const visibleHours = hours.slice(8, 23);

  const change = data.week?.change_pct ?? 0;
  const changeLabel = change > 0 ? `+${change}%` : `${change}%`;

  return (
    <div className="fade-in">
      <div className="header">
        <div>
          <h2 style={{fontStyle:'italic'}}>{greetingByHour(now.getHours())}{me?.name ? `, ${me.name.split(' ')[0]}` : ''}.</h2>
          <div className="muted" style={{marginTop:6}}>{todayLabel(now)} · ваше ателье цветов</div>
        </div>
        <div className="row">
          <button className="ghost" onClick={() => nav('/orders')}>
            Все заказы <IconChevron size={14} />
          </button>
        </div>
      </div>

      {/* KPI ленты */}
      <div className="kpi-grid">
        <div className="kpi accent-terracotta">
          <div className="kpi-label">Выручка сегодня</div>
          <div className="kpi-value mono">
            {Math.round(today.revenue || 0).toLocaleString('ru-RU')}
            <span className="unit">{currencySymbol(ccy)}</span>
          </div>
          <div className="kpi-sub">{today.paid_orders || 0} {pluralOrders(today.paid_orders || 0)} оплачено</div>
        </div>
        <div className="kpi accent-botanic">
          <div className="kpi-label">Заказов за день</div>
          <div className="kpi-value">{today.orders || 0}</div>
          <div className="kpi-sub">всего поступило</div>
        </div>
        <div className="kpi accent-ochre">
          <div className="kpi-label">Выручка за неделю</div>
          <div className="kpi-value mono">
            {Math.round(data.week?.revenue || 0).toLocaleString('ru-RU')}
            <span className="unit">{currencySymbol(ccy)}</span>
          </div>
          <div className={`kpi-sub ${change > 0 ? 'up' : change < 0 ? 'down' : ''}`}>
            {changeLabel} к прошлой неделе
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">За месяц</div>
          <div className="kpi-value mono">
            {Math.round(data.month?.revenue || 0).toLocaleString('ru-RU')}
            <span className="unit">{currencySymbol(ccy)}</span>
          </div>
          <div className="kpi-sub">30 дней</div>
        </div>
      </div>

      {/* Главный разворот «тетради»: слева — заказы дня + часы, справа — диалоги и каналы */}
      <div className="dash-grid">
        <div className="card">
          <div className="header" style={{marginBottom:12}}>
            <h3 className="serif" style={{fontStyle:'italic'}}>Заказы сегодня</h3>
            <button className="ghost small" onClick={() => nav('/orders')}>Канбан <IconChevron size={12} /></button>
          </div>
          {(today.orders_list || []).length === 0 ? (
            <div className="empty-state">
              <IconBouquet size={28} /> <div style={{marginTop:8}}>Сегодня ещё пусто. Скоро будут букеты.</div>
            </div>
          ) : (
            (today.orders_list || []).slice(0, 6).map(o => (
              <div key={o.id} className="dash-list-item">
                <div className="left" style={{minWidth:0}}>
                  <span className={`badge ${o.status}`}>{STATUS_LABELS[o.status] || o.status}</span>
                  <div style={{minWidth:0}}>
                    <div className="name">
                      {o.details?.name || `Заказ #${o.id}`}
                      <span className="muted mono" style={{marginLeft:8}}>#{o.id}</span>
                    </div>
                    <div className="sub">
                      {timeOfDay(o.created_at)} · {(o.items || []).map(i => i.name).filter(Boolean).slice(0, 2).join(', ') || '—'}
                    </div>
                  </div>
                </div>
                <div className="mono" style={{fontWeight:600}}>{formatMoney(o.total, ccy)}</div>
              </div>
            ))
          )}

          <div className="divider" />
          <div className="muted" style={{marginBottom:8, fontSize:12, letterSpacing:'0.08em', textTransform:'uppercase', fontWeight:600}}>
            Поступления по часам
          </div>
          <div className="hour-chart">
            {visibleHours.map(h => {
              const ratio = h.count / maxHour;
              return (
                <div
                  key={h.hour}
                  className={`hour-bar ${h.count > 0 ? 'has' : ''}`}
                  style={{ height: `${Math.max(2, ratio * 100)}%` }}
                  title={`${h.hour}:00 — ${h.count}`}
                >
                  {h.count > 0 && <span className="hour-tip">{h.hour}:00 · {h.count}</span>}
                </div>
              );
            })}
          </div>
          <div className="hour-axis">
            {visibleHours.filter((_, i) => i % 2 === 0).map(h => (
              <span key={h.hour}>{h.hour}</span>
            ))}
          </div>
        </div>

        <div>
          {/* Нужен менеджер */}
          <div className="card">
            <div className="header" style={{marginBottom:8}}>
              <h3 className="serif" style={{fontStyle:'italic'}}>Нужен ты</h3>
              {(conv.handoff || 0) > 0 && (
                <span className="badge handoff">{conv.handoff}</span>
              )}
            </div>
            {(conv.handoff || 0) === 0 && (conv.pending_payment || 0) === 0 ? (
              <div className="empty-state" style={{padding:'18px 8px'}}>
                <IconSparkle size={22} />
                <div style={{marginTop:6}}>Все диалоги под контролем AI.</div>
              </div>
            ) : (
              <>
                {(conv.handoff || 0) > 0 && (
                  <div className="dash-list-item" style={{cursor:'pointer'}} onClick={() => nav('/conversations?filter=handoff')}>
                    <div className="left">
                      <IconChat size={20} />
                      <div>
                        <div className="name">Диалоги ждут ответа</div>
                        <div className="sub">AI передал {conv.handoff} {pluralDialogs(conv.handoff)} менеджеру</div>
                      </div>
                    </div>
                    <IconChevron size={16} />
                  </div>
                )}
                {(conv.pending_payment || 0) > 0 && (
                  <div className="dash-list-item" style={{cursor:'pointer'}} onClick={() => nav('/conversations?filter=pending_payment')}>
                    <div className="left">
                      <IconBag size={20} />
                      <div>
                        <div className="name">Ждут оплаты</div>
                        <div className="sub">{conv.pending_payment} {pluralDialogs(conv.pending_payment)} в процессе</div>
                      </div>
                    </div>
                    <IconChevron size={16} />
                  </div>
                )}
              </>
            )}
            <div className="divider" />
            <div className="row" style={{justifyContent:'space-between'}}>
              <span className="muted">Активные с AI</span>
              <span className="mono" style={{fontWeight:600}}>{conv.active || 0}</span>
            </div>
          </div>

          {/* Каналы */}
          <div className="card">
            <h3 className="serif" style={{fontStyle:'italic', marginBottom:10}}>Откуда заказы</h3>
            {Object.keys(data.by_channel || {}).length === 0 ? (
              <div className="muted">Пока нет статистики по каналам.</div>
            ) : (
              Object.entries(data.by_channel).map(([ch, n]) => {
                const meta = CHANNEL_META[ch] || { label: ch || 'другое', icon: IconChat };
                const Icon = meta.icon;
                return (
                  <div key={ch} className="dash-list-item">
                    <div className="left">
                      <Icon size={18} />
                      <span style={{fontWeight:600}}>{meta.label}</span>
                    </div>
                    <span className="mono">{n}</span>
                  </div>
                );
              })
            )}
          </div>

          {/* Топ продаж */}
          {(data.top_products || []).length > 0 && (
            <div className="card">
              <h3 className="serif" style={{fontStyle:'italic', marginBottom:10}}>Топ за месяц</h3>
              {data.top_products.map(p => (
                <div key={p.name} className="dash-list-item">
                  <div className="left">
                    <IconBouquet size={18} />
                    <div>
                      <div className="name">{p.name}</div>
                      <div className="sub">{p.qty} шт</div>
                    </div>
                  </div>
                  <span className="mono">{formatMoney(p.revenue, ccy)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function pluralOrders(n) {
  const m = n % 10, t = n % 100;
  if (t >= 11 && t <= 14) return 'заказов';
  if (m === 1) return 'заказ';
  if (m >= 2 && m <= 4) return 'заказа';
  return 'заказов';
}
function pluralDialogs(n) {
  const m = n % 10, t = n % 100;
  if (t >= 11 && t <= 14) return 'диалогов';
  if (m === 1) return 'диалог';
  if (m >= 2 && m <= 4) return 'диалога';
  return 'диалогов';
}
