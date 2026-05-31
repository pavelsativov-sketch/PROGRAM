import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { IconWhatsapp, IconInstagram, IconCheck, IconClose } from '../icons.jsx';

export default function Channels() {
  return (
    <div className="fade-in">
      <div className="header">
        <div>
          <h2 style={{fontStyle:'italic'}}>Каналы связи</h2>
          <div className="muted">Подключите мессенджеры — клиенты будут писать туда, а AI отвечать здесь.</div>
        </div>
      </div>
      <div className="grid-2">
        <WhatsAppCard />
        <InstagramCard />
      </div>
    </div>
  );
}

function StatusBadge({ ok, label }) {
  return <span className={`badge ${ok ? 'paid' : 'pending_payment'}`}>{label}</span>;
}

function WhatsAppCard() {
  const [status, setStatus] = useState(null);
  const [qr, setQr] = useState(null);
  const [starting, setStarting] = useState(false);

  const refresh = async () => {
    try {
      const s = await api.wa.status();
      setStatus(s);
      if (s.status === 'qr') { const q = await api.wa.qr(); setQr(q.qr); } else { setQr(null); }
    } catch (e) { setStatus({ status: 'down', error: e.message }); }
  };
  useEffect(() => { refresh(); const t = setInterval(refresh, 3000); return () => clearInterval(t); }, []);

  const connect = async () => { setStarting(true); try { await api.wa.connect(); await refresh(); } finally { setStarting(false); } };
  const logout = async () => { if (!confirm('Отключить WhatsApp?')) return; await api.wa.logout(); refresh(); };

  const ready = status?.status === 'ready';

  return (
    <div className="channel-card">
      <div className="channel-head">
        <div className="row">
          <span className="channel-icon wa"><IconWhatsapp size={20} /></span>
          <div>
            <h3 style={{margin:0}}>WhatsApp</h3>
            <div className="muted" style={{fontSize:12}}>{ready ? `+${status.me}` : 'Личный мессенджер магазина'}</div>
          </div>
        </div>
        <StatusBadge ok={ready} label={status?.status || '…'} />
      </div>

      {status?.status === 'down' && <div className="note-box">WhatsApp-мост сейчас недоступен. Проверьте, что контейнер `wa-bridge` запущен.</div>}

      {(status?.status === 'disconnected' || !status) && status?.status !== 'down' && (
        <button onClick={connect} disabled={starting}>{starting ? 'Запуск…' : 'Подключить WhatsApp'}</button>
      )}
      {status?.status === 'starting' && <div className="muted"><span className="pulse-dot" /> Инициализация… подождите несколько секунд.</div>}
      {status?.status === 'qr' && qr && (
        <div>
          <div className="muted" style={{marginBottom:10}}>WhatsApp → <b>Настройки</b> → <b>Связанные устройства</b> → <b>Привязать устройство</b> → отсканируйте QR.</div>
          <img src={qr} alt="QR" style={{width:240, height:240, border:'1px solid var(--line)', borderRadius:'var(--r-sm)', padding:8, background:'#fff'}} />
        </div>
      )}
      {ready && (
        <div className="row" style={{justifyContent:'space-between'}}>
          <span style={{color:'var(--ok)'}}><IconCheck size={16} /> Подключено</span>
          <button className="ghost small" onClick={logout}><IconClose size={14} /> Отключить</button>
        </div>
      )}
    </div>
  );
}

function InstagramCard() {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [hint, setHint] = useState('');
  const [showLogin, setShowLogin] = useState(false);
  const [form, setForm] = useState({ username: '', password: '', code: '', proxy: '' });

  const refresh = () => api.ig.status()
    .then(s => setStatus(s))
    .catch(() => setStatus({ status: 'disconnected', connected: false }));
  useEffect(() => { refresh(); const t = setInterval(refresh, 6000); return () => clearInterval(t); }, []);

  const connected = status?.connected || status?.connected_db;

  const submit = async (e) => {
    e.preventDefault();
    if (!form.username || !form.password) return;
    setBusy(true); setError(''); setHint('');
    try {
      const r = await api.ig.login(form);
      if (r.ok) {
        setShowLogin(false);
        setForm({ username: '', password: '', code: '', proxy: '' });
        await refresh();
      } else {
        setHint(r.hint || '');
        setError(r.error || 'Не удалось войти');
      }
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    if (!confirm('Отключить Instagram-канал?')) return;
    await api.ig.logout();
    refresh();
  };

  return (
    <div className="channel-card">
      <div className="channel-head">
        <div className="row">
          <span className="channel-icon ig"><IconInstagram size={20} /></span>
          <div>
            <h3 style={{margin:0}}>Instagram Direct</h3>
            <div className="muted" style={{fontSize:12}}>{status?.username ? `@${status.username}` : 'Personal account · DM полинг'}</div>
          </div>
        </div>
        <StatusBadge ok={connected} label={status?.status || (connected ? 'connected' : 'disconnected')} />
      </div>

      <div className="note-box" style={{marginBottom:12}}>
        <b>Важно:</b> Meta агрессивно блокирует серверные IP. Для стабильной работы укажите <b>residential / mobile прокси</b>. Без прокси канал может выдать checkpoint при первом входе.
      </div>

      {!connected && !showLogin && (
        <button onClick={() => setShowLogin(true)}>Подключить Instagram</button>
      )}

      {!connected && showLogin && (
        <form onSubmit={submit}>
          <label>Логин Instagram</label>
          <input value={form.username} onChange={e => setForm({...form, username: e.target.value})} placeholder="myflorist" autoComplete="off" />
          <label>Пароль</label>
          <input type="password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} autoComplete="off" />
          <label>Прокси (опционально, рекомендуется)</label>
          <input value={form.proxy} onChange={e => setForm({...form, proxy: e.target.value})} placeholder="http://user:pass@host:port" />
          <label>Код двухфакторки / e-mail (если запросит)</label>
          <input value={form.code} onChange={e => setForm({...form, code: e.target.value})} placeholder="123456" />
          {error && (
            <div className="err" style={{marginTop:10}}>
              {error}
              {hint === 'ip_blocked' && <div style={{marginTop:6, fontSize:12}}>Похоже, IP заблокирован Meta. Подключите прокси и попробуйте снова.</div>}
              {hint === 'challenge_required' && <div style={{marginTop:6, fontSize:12}}>Instagram прислал код безопасности на email/sms — введите его в поле выше.</div>}
              {hint === 'bad_password' && <div style={{marginTop:6, fontSize:12}}>Логин или пароль неверны.</div>}
              {hint === 'bad_proxy' && <div style={{marginTop:6, fontSize:12}}>Проверьте формат прокси-строки.</div>}
            </div>
          )}
          <div className="row" style={{marginTop:12}}>
            <button type="submit" disabled={busy}>{busy ? 'Подключаемся…' : 'Войти'}</button>
            <button type="button" className="secondary" onClick={() => { setShowLogin(false); setError(''); }}>Отмена</button>
          </div>
        </form>
      )}

      {connected && (
        <div className="row" style={{justifyContent:'space-between'}}>
          <span style={{color:'var(--ok)'}}>
            <IconCheck size={16} /> Подключено как @{status?.username || '—'}
          </span>
          <button className="ghost small" onClick={logout}><IconClose size={14} /> Отключить</button>
        </div>
      )}
    </div>
  );
}
