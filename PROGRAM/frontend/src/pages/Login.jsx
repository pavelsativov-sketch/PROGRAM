import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { authStore } from '../auth';
import { IconCheck } from '../icons.jsx';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    setErr(''); setLoading(true);
    try {
      await api.auth.login({ email, password });
      authStore.setLoggedIn(true);
      nav('/dashboard');
    } catch (e) { setErr(e.message); } finally { setLoading(false); }
  };

  return (
    <div className="auth-split">
      <aside className="auth-aside">
        <Link to="/" className="auth-aside-brand">Floral<span>·</span><small>AI</small></Link>
        <div className="auth-aside-mid">
          <h2>С возвращением.<br/>Ваш AI-флорист уже на смене.</h2>
          <ul className="auth-aside-list">
            <li><IconCheck /> Диалоги, заказы и счета — в одном окне</li>
            <li><IconCheck /> Бот отвечает клиентам за секунды</li>
            <li><IconCheck /> Полный контроль и передача менеджеру</li>
          </ul>
        </div>
        <div className="auth-aside-foot">продажи цветов на автопилоте</div>
      </aside>

      <div className="auth-form-pane">
        <form className="auth-form" onSubmit={submit}>
          <h1>Вход в ателье</h1>
          <div className="auth-form-sub">Рады видеть вас снова</div>
          <label>Email</label>
          <input type="email" required value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" placeholder="you@flowers.shop" />
          <label>Пароль</label>
          <input type="password" required value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" placeholder="••••••••" />
          {err && <div className="err">{err}</div>}
          <button disabled={loading} className="lp-btn-lg" style={{width:'100%', marginTop:18, justifyContent:'center'}}>
            {loading ? <span className="pulse-dot" /> : 'Войти'}
          </button>
          <div className="muted" style={{marginTop:16, textAlign:'center'}}>
            Впервые здесь? <Link to="/signup">создать ателье</Link>
          </div>
        </form>
      </div>
    </div>
  );
}
