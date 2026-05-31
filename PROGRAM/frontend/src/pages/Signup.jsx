import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { authStore } from '../auth';
import { IconCheck } from '../icons.jsx';

export default function Signup() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    setErr(''); setLoading(true);
    try {
      await api.auth.signup({ email, password, name });
      authStore.setLoggedIn(true);
      nav('/dashboard');
    } catch (e) { setErr(e.message); } finally { setLoading(false); }
  };

  return (
    <div className="auth-split">
      <aside className="auth-aside">
        <Link to="/" className="auth-aside-brand">Floral<span>·</span><small>AI</small></Link>
        <div className="auth-aside-mid">
          <h2>Дайте магазину<br/>продавца, который не спит.</h2>
          <ul className="auth-aside-list">
            <li><IconCheck /> Запуск за один день, без программистов</li>
            <li><IconCheck /> Бесплатный AI-агент на старте</li>
            <li><IconCheck /> WhatsApp и Instagram из коробки</li>
          </ul>
        </div>
        <div className="auth-aside-foot">продажи цветов на автопилоте</div>
      </aside>

      <div className="auth-form-pane">
        <form className="auth-form" onSubmit={submit}>
          <h1>Создать ателье</h1>
          <div className="auth-form-sub">Бесплатно — первые продажи уже сегодня</div>
          <label>Название магазина</label>
          <input required value={name} onChange={e => setName(e.target.value)} placeholder="Цветочная лавка «Весна»" />
          <label>Email</label>
          <input type="email" required value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" placeholder="you@flowers.shop" />
          <label>Пароль (мин. 8 символов)</label>
          <input type="password" minLength={8} required value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" placeholder="••••••••" />
          {err && <div className="err">{err}</div>}
          <button disabled={loading} className="lp-btn-lg" style={{width:'100%', marginTop:18, justifyContent:'center'}}>
            {loading ? <span className="pulse-dot" /> : 'Создать ателье'}
          </button>
          <div className="muted" style={{marginTop:16, textAlign:'center'}}>
            Уже регистрировались? <Link to="/login">войти</Link>
          </div>
        </form>
      </div>
    </div>
  );
}
