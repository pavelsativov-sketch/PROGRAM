import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { currencySymbol } from '../format';

const RANGES = [
  { days: 7, label: '7 дней' },
  { days: 30, label: '30 дней' },
  { days: 90, label: '90 дней' },
];

export default function Analytics() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState('');

  useEffect(() => {
    setData(null);
    api.analytics.report(days).then(setData).catch(e => setError(String(e.message || e)));
  }, [days]);

  if (error) return <div className="card"><div className="err">{error}</div></div>;
  if (!data) {
    return <div className="card empty-state"><span className="pulse-dot" /> считаем аналитику…</div>;
  }

  const ccy = data.currency || 'RUB';
  const sym = currencySymbol(ccy);
  const f = data.funnel || {};
  const totals = data.totals || {};
  const rev = data.revenue_by_day || [];
  const peak = data.peak_hours || [];
  const top = data.top_products || [];
  const aiM = data.ai_vs_manual || { ai: 0, manual: 0, ai_pct: 0 };

  const maxRev = Math.max(1, ...rev.map(d => d.revenue));
  const visiblePeak = peak.slice(7, 23);
  const maxPeak = Math.max(1, ...visiblePeak.map(h => h.count));
  const aiTotal = (aiM.ai || 0) + (aiM.manual || 0);

  const fmt = (n) => Math.round(n || 0).toLocaleString('ru-RU');

  return (
    <div className="fade-in">
      <div className="header">
        <div>
          <h2 style={{ fontStyle: 'italic' }}>Аналитика</h2>
          <div className="muted" style={{ marginTop: 6 }}>воронка продаж, выручка, часы пик и эффективность бота</div>
        </div>
        <div className="seg">
          {RANGES.map(r => (
            <button key={r.days} className={days === r.days ? 'active' : ''} onClick={() => setDays(r.days)}>{r.label}</button>
          ))}
        </div>
      </div>

      {/* KPI */}
      <div className="kpi-grid">
        <div className="kpi accent-terracotta">
          <div className="kpi-label">Выручка за период</div>
          <div className="kpi-value mono">{fmt(totals.revenue)}<span className="unit">{sym}</span></div>
          <div className="kpi-sub">{totals.paid_orders || 0} оплат</div>
        </div>
        <div className="kpi accent-botanic">
          <div className="kpi-label">Диалогов</div>
          <div className="kpi-value">{f.dialogs || 0}</div>
          <div className="kpi-sub">за {data.days} дн.</div>
        </div>
        <div className="kpi accent-ochre">
          <div className="kpi-label">Конверсия в счёт</div>
          <div className="kpi-value">{f.invoice_rate || 0}<span className="unit">%</span></div>
          <div className="kpi-sub">{f.invoiced || 0} счетов</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Конверсия в оплату</div>
          <div className="kpi-value">{f.paid_rate || 0}<span className="unit">%</span></div>
          <div className="kpi-sub">{f.paid || 0} оплачено</div>
        </div>
      </div>

      <div className="dash-grid">
        {/* Воронка */}
        <div className="card">
          <h3 className="serif" style={{ fontStyle: 'italic', marginBottom: 14 }}>Воронка продаж</h3>
          <Funnel
            steps={[
              { label: 'Диалоги', value: f.dialogs || 0, color: 'var(--botanic)' },
              { label: 'Счета', value: f.invoiced || 0, color: 'var(--ochre)' },
              { label: 'Оплаты', value: f.paid || 0, color: 'var(--terracotta)' },
            ]}
          />
        </div>

        {/* AI vs ручное */}
        <div className="card">
          <h3 className="serif" style={{ fontStyle: 'italic', marginBottom: 14 }}>AI vs менеджер</h3>
          {aiTotal === 0 ? (
            <div className="empty-state">Пока нет данных по диалогам</div>
          ) : (
            <div>
              <Donut ai={aiM.ai || 0} manual={aiM.manual || 0} />
              <div className="legend" style={{ marginTop: 16 }}>
                <div><span className="dot" style={{ background: 'var(--botanic)' }} /> Бот сам довёл — <b>{aiM.ai || 0}</b> ({aiM.ai_pct || 0}%)</div>
                <div><span className="dot" style={{ background: 'var(--terracotta)' }} /> Понадобился менеджер — <b>{aiM.manual || 0}</b></div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Выручка по дням */}
      <div className="card" style={{ marginTop: 18 }}>
        <h3 className="serif" style={{ fontStyle: 'italic', marginBottom: 14 }}>Выручка по дням</h3>
        {rev.every(d => d.revenue === 0) ? (
          <div className="empty-state">Оплат за период пока нет</div>
        ) : (
          <div className="bars">
            {rev.map(d => (
              <div key={d.date} className="bar-col" title={`${d.date}: ${fmt(d.revenue)} ${sym} · ${d.orders} зак.`}>
                <div className="bar" style={{ height: `${Math.max(2, (d.revenue / maxRev) * 100)}%` }} />
              </div>
            ))}
          </div>
        )}
        <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
          {rev.length ? `${rev[0].date} — ${rev[rev.length - 1].date}` : ''}
        </div>
      </div>

      <div className="dash-grid" style={{ marginTop: 18 }}>
        {/* Часы пик */}
        <div className="card">
          <h3 className="serif" style={{ fontStyle: 'italic', marginBottom: 14 }}>Часы пик (заказы)</h3>
          {visiblePeak.every(h => h.count === 0) ? (
            <div className="empty-state">Недостаточно данных</div>
          ) : (
            <div className="bars">
              {visiblePeak.map(h => (
                <div key={h.hour} className="bar-col" title={`${h.hour}:00 — ${h.count}`}>
                  <div className="bar ochre" style={{ height: `${Math.max(2, (h.count / maxPeak) * 100)}%` }} />
                  <div className="bar-x">{h.hour}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Топ-букеты */}
        <div className="card">
          <h3 className="serif" style={{ fontStyle: 'italic', marginBottom: 14 }}>Топ-букеты</h3>
          {top.length === 0 ? (
            <div className="empty-state">Пока нет оплаченных заказов</div>
          ) : (
            <table className="tbl">
              <thead><tr><th>Букет</th><th>Шт.</th><th style={{ textAlign: 'right' }}>Выручка</th></tr></thead>
              <tbody>
                {top.map((p, i) => (
                  <tr key={i}>
                    <td>{p.name}</td>
                    <td>{p.qty}</td>
                    <td style={{ textAlign: 'right' }} className="mono">{fmt(p.revenue)} {sym}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function Funnel({ steps }) {
  const max = Math.max(1, ...steps.map(s => s.value));
  return (
    <div className="funnel">
      {steps.map((s, i) => {
        const prev = i > 0 ? steps[i - 1].value : null;
        const pct = prev ? (prev > 0 ? Math.round((s.value / prev) * 100) : 0) : null;
        return (
          <div key={s.label} className="funnel-row">
            <div className="funnel-meta"><span>{s.label}</span><b>{s.value}</b></div>
            <div className="funnel-track">
              <div className="funnel-fill" style={{ width: `${Math.max(4, (s.value / max) * 100)}%`, background: s.color }} />
            </div>
            {pct !== null && <div className="funnel-pct">{pct}% от пред. шага</div>}
          </div>
        );
      })}
    </div>
  );
}

function Donut({ ai, manual }) {
  const total = ai + manual || 1;
  const aiFrac = ai / total;
  const r = 54, c = 2 * Math.PI * r;
  const aiLen = aiFrac * c;
  return (
    <div style={{ display: 'flex', justifyContent: 'center' }}>
      <svg width="140" height="140" viewBox="0 0 140 140">
        <circle cx="70" cy="70" r={r} fill="none" stroke="var(--terracotta)" strokeWidth="18" />
        <circle
          cx="70" cy="70" r={r} fill="none" stroke="var(--botanic)" strokeWidth="18"
          strokeDasharray={`${aiLen} ${c - aiLen}`} strokeDashoffset={c / 4} transform="rotate(-90 70 70)"
          style={{ transition: 'stroke-dasharray .5s' }}
        />
        <text x="70" y="66" textAnchor="middle" fontSize="26" fontWeight="700" fill="var(--ink)">{Math.round(aiFrac * 100)}%</text>
        <text x="70" y="86" textAnchor="middle" fontSize="11" fill="#888">авто-ботом</text>
      </svg>
    </div>
  );
}
