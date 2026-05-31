import React, { useEffect, useState } from 'react';
import { NavLink, Route, Routes, Navigate, useNavigate } from 'react-router-dom';
import { api } from './api';
import { authStore } from './auth';
import {
  IconHome, IconFlow, IconLab, IconChat, IconBag,
  IconBouquet, IconLeaf, IconWrench, IconUsers, IconLogout, IconChart,
} from './icons.jsx';
import NotificationCenter from './components/NotificationCenter.jsx';
import Dashboard from './pages/Dashboard.jsx';
import FlowsList from './pages/FlowsList.jsx';
import FlowEditor from './pages/FlowEditor.jsx';
import Orders from './pages/Orders.jsx';
import Products from './pages/Products.jsx';
import Conversations from './pages/Conversations.jsx';
import Customers from './pages/Customers.jsx';
import Simulator from './pages/Simulator.jsx';
import Channels from './pages/Channels.jsx';
import Settings from './pages/Settings.jsx';
import Analytics from './pages/Analytics.jsx';
import Login from './pages/Login.jsx';
import Signup from './pages/Signup.jsx';
import Landing from './pages/Landing.jsx';

const NAV = [
  { to: '/dashboard',    label: 'Сегодня',    Icon: IconHome,    end: true },
  { to: '/orders',       label: 'Заказы',     Icon: IconBag },
  { to: '/conversations',label: 'Диалоги',    Icon: IconChat,    badge: 'handoff' },
  { to: '/customers',    label: 'Клиенты',    Icon: IconUsers },
  { to: '/analytics',    label: 'Аналитика',  Icon: IconChart },
  { to: '/products',     label: 'Каталог',    Icon: IconBouquet },
  { to: '/flows',        label: 'Сценарии',   Icon: IconFlow },
  { to: '/simulator',    label: 'Симулятор',  Icon: IconLab },
  { to: '/channels',     label: 'Каналы',     Icon: IconLeaf },
  { to: '/settings',     label: 'Настройки',  Icon: IconWrench },
];

function Layout({ children, full }) {
  const [me, setMe] = useState(null);
  const [handoffCount, setHandoffCount] = useState(0);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const lastHandoffRef = React.useRef(0);
  const nav = useNavigate();

  useEffect(() => { api.auth.me().then(setMe).catch(() => {}); }, []);

  // Web Push: при первом появлении handoff показываем системную нотификацию.
  // Запрашиваем разрешение лениво — только после первого «нужен менеджер».
  useEffect(() => {
    const tick = async () => {
      try {
        const list = await api.conversations.list('handoff');
        setHandoffCount(list.length);
        lastHandoffRef.current = list.length;
      } catch {}
    };
    tick();
    const t = setInterval(tick, 8000);
    return () => clearInterval(t);
  }, []);

  // Закрываем drawer при смене роута (на мобиле)
  const location = window.location.pathname;
  useEffect(() => { setDrawerOpen(false); }, [location]);

  const logout = async () => {
    try { await api.auth.logout(); } catch {}
    authStore.clear();
    nav('/login');
  };

  const onNavClick = () => setDrawerOpen(false);

  return (
    <div className="layout">
      <header className="topbar">
        <button className="menu-btn" onClick={() => setDrawerOpen(o => !o)} aria-label="Меню">☰</button>
        <span className="brand">Floral<span style={{color:'var(--terracotta)'}}>·</span></span>
        {handoffCount > 0 && <span className="nav-badge">{handoffCount}</span>}
        <div style={{marginLeft:'auto'}}><NotificationCenter /></div>
      </header>
      {drawerOpen && <div className="drawer-overlay open" onClick={() => setDrawerOpen(false)} />}
      <aside className={`sidebar ${drawerOpen ? 'open' : ''}`}>
        <div className="sidebar-brand">
          Floral<span className="brand-dot">·</span><small>ателье</small>
        </div>
        {me && (
          <div className="sidebar-shop">
            <b>{me.name}</b><br />
            {me.email}
          </div>
        )}
        <nav style={{display:'flex', flexDirection:'column', gap:0}}>
          {NAV.map(item => (
            <NavLink key={item.to} to={item.to} end={item.end} onClick={onNavClick} className={({isActive}) => isActive ? 'active' : ''}>
              <span className="row" style={{gap:10, flex:1}}>
                <span className="nav-icon"><item.Icon size={17} /></span>
                <span>{item.label}</span>
              </span>
              {item.badge === 'handoff' && handoffCount > 0 && (
                <span className="nav-badge">{handoffCount}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <a href="#" onClick={e => {e.preventDefault(); logout();}}>
            <span className="row" style={{gap:10}}><IconLogout size={16} /> <span>Выйти</span></span>
          </a>
        </div>
      </aside>
      <main className={full ? 'content full' : 'content'}>{children}</main>
    </div>
  );
}

function Private({ children, full }) {
  if (!authStore.loggedIn) return <Navigate to="/login" />;
  return <Layout full={full}>{children}</Layout>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/" element={authStore.loggedIn ? <Navigate to="/dashboard" /> : <Landing />} />
      <Route path="/dashboard" element={<Private><Dashboard /></Private>} />
      <Route path="/flows" element={<Private><FlowsList /></Private>} />
      <Route path="/flows/:id" element={<Private full><FlowEditor /></Private>} />
      <Route path="/simulator" element={<Private><Simulator /></Private>} />
      <Route path="/conversations" element={<Private><Conversations /></Private>} />
      <Route path="/conversations/:id" element={<Private><Conversations /></Private>} />
      {/* legacy /manager → редирект на /conversations с фильтром handoff */}
      <Route path="/manager" element={<Navigate to="/conversations?filter=handoff" replace />} />
      <Route path="/manager/:id" element={<Navigate to="/conversations" replace />} />
      <Route path="/orders" element={<Private><Orders /></Private>} />
      <Route path="/customers" element={<Private><Customers /></Private>} />
      <Route path="/customers/:id" element={<Private><Customers /></Private>} />
      <Route path="/products" element={<Private><Products /></Private>} />
      <Route path="/channels" element={<Private><Channels /></Private>} />
      <Route path="/settings" element={<Private><Settings /></Private>} />
      <Route path="/analytics" element={<Private><Analytics /></Private>} />
    </Routes>
  );
}
