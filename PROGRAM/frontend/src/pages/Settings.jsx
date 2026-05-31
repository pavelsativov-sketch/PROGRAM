import React, { useEffect, useState } from 'react';
import { api } from '../api';

export default function Settings() {
  const [me, setMe] = useState(null);
  const [form, setForm] = useState({});
  const [saved, setSaved] = useState('');

  useEffect(() => {
    api.auth.me().then(m => {
      setMe(m);
      setForm({
        name: m.name,
        currency: m.currency,
        ai_provider: m.ai_provider || 'free',
        ai_model: m.ai_model || '',
        ai_api_key: '',
        kaspi_phone: m.kaspi_phone || '',
        kaspi_name: m.kaspi_name || '',
        kaspi_qr_url: m.kaspi_qr_url || '',
        payment_instructions: m.payment_instructions || '',
        business_hours: m.business_hours || defaultBusinessHours(),
        tg_bot_token: '',
        tg_chat_id: m.tg_chat_id || '',
      });
    });
  }, []);

  const flash = (text) => {
    setSaved(text);
    setTimeout(() => setSaved(''), 2500);
  };

  const save = async () => {
    const d = { ...form };
    if (!d.ai_api_key) delete d.ai_api_key;
    try {
      const m = await api.auth.updateMe(d);
      setMe(m);
      flash('Сохранено');
    } catch (e) {
      flash('Ошибка: ' + (e.message || e));
    }
  };

  const clearKey = async () => {
    if (!confirm('Очистить AI-ключ магазина и использовать общий ключ сервера?')) return;
    try {
      const m = await api.auth.updateMe({ ai_api_key: '' });
      setMe(m);
      setForm({ ...form, ai_api_key: '' });
      flash('AI-ключ очищен');
    } catch (e) {
      flash('Ошибка: ' + (e.message || e));
    }
  };

  const uploadKaspiQr = async (file) => {
    if (!file) return;
    try {
      const r = await api.orders.uploadProductImage(file);
      setForm(f => ({ ...f, kaspi_qr_url: r.url }));
      flash('Kaspi QR загружен');
    } catch (e) {
      flash('Ошибка загрузки: ' + (e.message || e));
    }
  };

  if (!me) return <div>Загрузка...</div>;

  const isError = saved.startsWith('Ошибка');

  return (
    <div className="fade-in">
      <div className="header">
        <div>
          <h2 style={{fontStyle:'italic'}}>Настройки</h2>
          <div className="muted">Магазин, AI-бот, способы оплаты.</div>
        </div>
      </div>

      <div className="card" style={{maxWidth:680}}>
        <h3 style={{marginTop:0, fontStyle:'italic'}}>Магазин</h3>
        <label>Название магазина</label>
        <input value={form.name || ''} onChange={e => setForm({...form, name: e.target.value})} />
        <label>Валюта</label>
        <select value={form.currency || 'RUB'} onChange={e => setForm({...form, currency: e.target.value})}>
          <option value="RUB">RUB · ₽ — Россия</option>
          <option value="KZT">KZT · ₸ — Казахстан</option>
          <option value="UAH">UAH · ₴ — Украина</option>
          <option value="BYN">BYN · Br — Беларусь</option>
          <option value="USD">USD · $</option>
          <option value="EUR">EUR · €</option>
          <option value="GBP">GBP · £</option>
        </select>
        <div className="row" style={{marginTop:14}}>
          <button onClick={save}>Сохранить</button>
          {saved && <span style={{color: isError ? 'var(--err)' : 'var(--ok)'}}>{saved}</span>}
        </div>
      </div>

      <div className="card" style={{maxWidth:680}}>
        <h3 style={{marginTop:0}}>AI-бот</h3>
        <label>Провайдер</label>
        <select value={form.ai_provider} onChange={e => setForm({...form, ai_provider: e.target.value})}>
          <option value="free">Бесплатный (без ключа)</option>
          <option value="anthropic">Anthropic Claude</option>
          <option value="openai">OpenAI</option>
          <option value="gemini">Google Gemini</option>
        </select>
        <label>Модель</label>
        <input value={form.ai_model || ''} onChange={e => setForm({...form, ai_model: e.target.value})}
          placeholder={
            form.ai_provider === 'openai' ? 'gpt-4o-mini'
            : form.ai_provider === 'gemini' ? 'gemini-2.5-flash'
            : form.ai_provider === 'anthropic' ? 'claude-haiku-4-5'
            : 'openai'
          } />
        {form.ai_provider === 'free' && (
          <div style={{fontSize:12, color:'#888', marginTop:4}}>
            Публичный бесплатный API (Pollinations.ai). Ключ не требуется. Для prod лучше платный провайдер.
          </div>
        )}
        <label>API-ключ</label>
        <input type="password" value={form.ai_api_key || ''} onChange={e => setForm({...form, ai_api_key: e.target.value})} placeholder="Оставьте пустым, чтобы не менять текущий ключ" />
        <div className="row" style={{marginTop:16}}>
          <button onClick={save}>Сохранить AI-настройки</button>
          <button className="secondary" onClick={clearKey}>Использовать ключ сервера</button>
        </div>
      </div>

      <div className="card" style={{maxWidth:680}}>
        <h3 style={{marginTop:0}}>Оплата Kaspi</h3>
        <label>Телефон Kaspi</label>
        <input value={form.kaspi_phone || ''} onChange={e => setForm({...form, kaspi_phone: e.target.value})} placeholder="+7 777 000 00 00" />
        <label>Имя получателя</label>
        <input value={form.kaspi_name || ''} onChange={e => setForm({...form, kaspi_name: e.target.value})} placeholder="Имя владельца или название компании" />
        <label>QR-код Kaspi</label>
        <input type="file" accept="image/*" onChange={e => uploadKaspiQr(e.target.files?.[0])} />
        {form.kaspi_qr_url && (
          <div style={{marginTop:10}}>
            <img src={form.kaspi_qr_url} style={{width:180, height:180, objectFit:'contain', border:'1px solid var(--line)', borderRadius:'var(--r-sm)'}} />
          </div>
        )}
        <label>Инструкция по оплате</label>
        <textarea rows={3} value={form.payment_instructions || ''} onChange={e => setForm({...form, payment_instructions: e.target.value})} placeholder="Оплатите через Kaspi, укажите номер заказа в комментарии и нажмите «Я оплатил через Kaspi»." />
        <div className="row" style={{marginTop:16}}>
          <button onClick={save}>Сохранить Kaspi-настройки</button>
          {saved && <span style={{color: isError ? 'var(--err)' : 'var(--ok)'}}>{saved}</span>}
        </div>
      </div>
    </div>
  );
}
