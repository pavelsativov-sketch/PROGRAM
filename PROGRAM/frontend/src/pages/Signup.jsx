import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { authStore } from '../auth';

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
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <h1>Floral<span className="accent">·</span></h1>
        <div className="auth-sub">создать ателье</div>
        <label>Название магазина</label>
        <input required value={name} onChange={e => setName(e.target.value)} placeholder="Цветочная лавка «Весна»" />
        <label>Email</label>
        <input type="email" required value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" />
        <label>Пароль (мин. 8 символов)</label>
        <input type="password" minLength={8} required value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" />
        {err && <div className="err">{err}</div>}
        <button disabled={loading} style={{width:'100%', marginTop:18, justifyContent:'center'}}>
          {loading ? <span className="pulse-dot" /> : 'Создать'}
        </button>
        <div className="muted" style={{marginTop:14, textAlign:'center'}}>
          Уже регистрировались? <Link to="/login">войти</Link>
        </div>
      </form>
    </div>
  );
}
