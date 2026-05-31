import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { authStore } from '../auth';

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
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <h1>Floral<span className="accent">·</span></h1>
        <div className="auth-sub">ателье цветов</div>
        <label>Email</label>
        <input type="email" required value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" />
        <label>Пароль</label>
        <input type="password" required value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" />
        {err && <div className="err">{err}</div>}
        <button disabled={loading} style={{width:'100%', marginTop:18, justifyContent:'center'}}>
          {loading ? <span className="pulse-dot" /> : 'Войти'}
        </button>
        <div className="muted" style={{marginTop:14, textAlign:'center'}}>
          Впервые здесь? <Link to="/signup">создать ателье</Link>
        </div>
      </form>
    </div>
  );
}
