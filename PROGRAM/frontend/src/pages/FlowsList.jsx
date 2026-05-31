import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

export default function FlowsList() {
  const [flows, setFlows] = useState([]);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const nav = useNavigate();

  const load = () => api.flows.list().then(setFlows).catch(e => setError(String(e.message || e)));
  useEffect(() => { load(); }, []);

  const create = async () => {
    setError('');
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Введите название сценария');
      return;
    }
    setBusy(true);
    try {
      const f = await api.flows.create({
        name: trimmed,
        description: '',
        is_active: false,
        graph: { nodes: [{ id: 'n1', type: 'default', position: {x:100,y:100}, data: { kind: 'start', label: 'Старт' }}], edges: [] },
      });
      setName('');
      nav(`/flows/${f.id}`);
    } catch (e) {
      setError('Не удалось создать: ' + (e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e) => { if (e.key === 'Enter') create(); };

  const activate = async (id) => { try { await api.flows.activate(id); load(); } catch (e) { setError(String(e.message || e)); } };
  const remove = async (id) => { if (confirm('Удалить сценарий?')) { try { await api.flows.remove(id); load(); } catch (e) { setError(String(e.message || e)); } } };

  return (
    <div className="fade-in">
      <div className="header">
        <div>
          <h2 style={{margin:0, fontStyle:'italic'}}>Сценарии</h2>
          <div className="muted">Граф диалога AI-бота. Активный бывает только один.</div>
        </div>
      </div>
      <div className="card">
        <div className="row">
          <input placeholder="Название нового сценария" value={name} onChange={e => setName(e.target.value)} onKeyDown={onKey} />
          <button onClick={create} disabled={busy}>{busy ? 'Создание...' : 'Создать'}</button>
          <button className="secondary" onClick={async () => {
            if (!confirm('Создать и активировать AI-агент? Текущие сценарии останутся, но деактивируются.')) return;
            try { await api.flows.seedAgent(); load(); } catch (e) { setError(String(e.message || e)); }
          }}>🤖 Создать AI-агент</button>
        </div>
        {error && <div style={{color:'#dc2626', marginTop:8}}>{error}</div>}
        <div className="muted" style={{marginTop: 8}}>
          AI-агент — один узел, который сам ведёт диалог, собирает данные и оформляет счёт. Умнее скриптованных флоу.
        </div>
      </div>
      <div className="card">
        <table>
          <thead><tr><th>Название</th><th>Статус</th><th>Обновлён</th><th></th></tr></thead>
          <tbody>
            {flows.map(f => (
              <tr key={f.id}>
                <td><a href={`/flows/${f.id}`} onClick={e => {e.preventDefault(); nav(`/flows/${f.id}`);}}>{f.name}</a><div className="muted">{f.description}</div></td>
                <td>{f.is_active ? <span className="badge paid">активен</span> : <span className="badge closed">неактивен</span>}</td>
                <td>{new Date(f.updated_at).toLocaleString()}</td>
                <td>
                  <div className="row">
                    {!f.is_active && <button className="small" onClick={() => activate(f.id)}>Активировать</button>}
                    <button className="small secondary" onClick={() => nav(`/flows/${f.id}`)}>Редактор</button>
                    <button className="small danger" onClick={() => remove(f.id)}>Удалить</button>
                  </div>
                </td>
              </tr>
            ))}
            {flows.length === 0 && <tr><td colSpan={4} className="muted">Нет сценариев. Создайте первый.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
