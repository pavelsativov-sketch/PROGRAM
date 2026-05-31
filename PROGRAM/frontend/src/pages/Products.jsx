import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { currencySymbol } from '../format';

const empty = {
  name: '',
  category: 'Букеты',
  description: '',
  price: 0,
  image_url: '',
  available_today: true,
  is_active: true,
};

export default function Products() {
  const [items, setItems] = useState([]);
  const [draft, setDraft] = useState(empty);
  const [editing, setEditing] = useState(null);
  const [filter, setFilter] = useState('all');
  const [busyUpload, setBusyUpload] = useState(false);
  const [me, setMe] = useState(null);

  const load = () => api.orders.products().then(setItems);
  useEffect(() => { load(); api.auth.me().then(setMe).catch(() => {}); }, []);
  const sym = currencySymbol(me?.currency || 'RUB');

  const categories = useMemo(() => {
    const all = [...new Set(items.map(p => p.category || 'Другое'))].sort();
    return ['all', ...all];
  }, [items]);

  const visible = useMemo(() => {
    if (filter === 'all') return items;
    return items.filter(p => (p.category || 'Другое') === filter);
  }, [items, filter]);

  const save = async () => {
    const payload = { ...draft, category: draft.category || 'Другое', price: Number(draft.price || 0) };
    if (editing) {
      await api.orders.updateProduct(editing, payload);
      setEditing(null);
    } else {
      await api.orders.createProduct(payload);
    }
    setDraft(empty);
    load();
  };

  const edit = (p) => {
    setEditing(p.id);
    setDraft({
      name: p.name,
      category: p.category || 'Другое',
      description: p.description,
      price: p.price,
      image_url: p.image_url,
      available_today: p.available_today,
      is_active: p.is_active,
    });
  };

  const remove = async (id) => {
    if (confirm('Удалить этот товар?')) {
      await api.orders.deleteProduct(id);
      load();
    }
  };

  const uploadImage = async (file) => {
    if (!file) return;
    setBusyUpload(true);
    try {
      const r = await api.orders.uploadProductImage(file);
      setDraft(d => ({ ...d, image_url: r.url }));
    } finally {
      setBusyUpload(false);
    }
  };

  return (
    <div className="fade-in">
      <div className="header">
        <div>
          <h2 style={{margin:0, fontStyle:'italic'}}>Каталог</h2>
          <div className="muted">Букеты, розы, категории, фотографии и наличие на сегодня.</div>
        </div>
      </div>

      <div className="card">
        <div className="grid-2">
          <div>
            <label>Название</label>
            <input value={draft.name} onChange={e => setDraft({...draft, name: e.target.value})} placeholder="Красные розы премиум" />
            <label>Категория</label>
            <input value={draft.category} onChange={e => setDraft({...draft, category: e.target.value})} placeholder="Букеты, Розы, Коробки" />
            <label>Описание</label>
            <textarea rows={4} value={draft.description} onChange={e => setDraft({...draft, description: e.target.value})} placeholder="Состав, размер, настроение, особенности доставки..." />
          </div>
          <div>
            <label>Цена</label>
            <input type="number" value={draft.price} onChange={e => setDraft({...draft, price: Number(e.target.value)})} />
            <label>Ссылка на изображение</label>
            <input value={draft.image_url} onChange={e => setDraft({...draft, image_url: e.target.value})} placeholder="/uploads/shop_1/..." />
            <label>Загрузить фото букета</label>
            <input type="file" accept="image/*" onChange={e => uploadImage(e.target.files?.[0])} />
            {busyUpload && <div className="muted" style={{marginTop:6}}>Загрузка...</div>}
            {draft.image_url && <img className="product-preview" src={draft.image_url} />}
            <label><input type="checkbox" checked={draft.available_today} onChange={e => setDraft({...draft, available_today: e.target.checked})} /> Есть сегодня</label>
            <label><input type="checkbox" checked={draft.is_active} onChange={e => setDraft({...draft, is_active: e.target.checked})} /> Показывать боту в каталоге</label>
          </div>
        </div>
        <div className="row" style={{marginTop:12}}>
          <button onClick={save} disabled={!draft.name.trim()}>{editing ? 'Сохранить товар' : 'Добавить товар'}</button>
          {editing && <button className="secondary" onClick={() => { setEditing(null); setDraft(empty); }}>Отмена</button>}
        </div>
      </div>

      <div className="filter-chips">
        {categories.map(c => (
          <button key={c} className={`chip ${filter === c ? 'on' : ''}`} onClick={() => setFilter(c)}>
            {c === 'all' ? 'Все' : c}
          </button>
        ))}
      </div>

      <div className="product-grid">
        {visible.length === 0 && (
          <div className="empty-state" style={{gridColumn:'1/-1', padding:'40px 16px'}}>
            Товаров пока нет. Добавьте первый букет выше.
          </div>
        )}
        {visible.map(p => (
          <div key={p.id} className={`product-card ${!p.is_active ? 'off' : ''}`}>
            <div className="product-img">
              {p.image_url ? <img src={p.image_url} /> : <span>Нет фото</span>}
            </div>
            <div className="product-body">
              <div className="product-top">
                <span className="product-category">{p.category || 'Другое'}</span>
                <span className={`badge ${p.available_today ? 'paid' : 'pending_payment'}`}>
                  {p.available_today ? 'есть сегодня' : 'под заказ'}
                </span>
              </div>
              <h3>{p.name}</h3>
              <p>{p.description || 'Описание пока не добавлено.'}</p>
              <div className="product-price">{Number(p.price || 0).toLocaleString('ru-RU')} {sym}</div>
              <div className="row">
                <button className="small secondary" onClick={() => edit(p)}>Править</button>
                <button className="small danger" onClick={() => remove(p.id)}>Удалить</button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
