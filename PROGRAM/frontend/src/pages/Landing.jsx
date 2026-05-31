import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  IconWhatsapp, IconInstagram, IconFlow, IconBag, IconUsers, IconSparkle,
  IconCheck, IconBouquet, IconChat, IconLab,
} from '../icons.jsx';

const FEATURES = [
  { icon: IconSparkle, title: 'AI-продавец 24/7', text: 'Живой флорист-консультант ведёт клиента от «Здравствуйте» до оплаты счёта — без выходных, ночью и в пик 8 марта.' },
  { icon: IconWhatsapp, title: 'WhatsApp и Instagram', text: 'Подключите свои аккаунты за пару минут. Все переписки — в одном окне, ничего не теряется.' },
  { icon: IconFlow, title: 'Визуальный редактор', text: 'Сценарий диалога собирается мышкой, без программистов. Меняйте логику продаж на лету.' },
  { icon: IconBag, title: 'Счета и оплата', text: 'Бот сам формирует заказ и присылает защищённую ссылку на оплату. Деньги — на вашем счёте.' },
  { icon: IconUsers, title: 'CRM и клиенты', text: 'История заказов, повторные продажи, LTV каждого клиента — автоматически и в одном месте.' },
  { icon: IconLab, title: 'Полный контроль', text: 'Менеджер видит каждый диалог и в один клик забирает разговор у бота, когда нужно.' },
];

const STEPS = [
  { n: '01', title: 'Подключите мессенджер', text: 'WhatsApp или Instagram магазина — через QR-код, без смены номера.' },
  { n: '02', title: 'Настройте каталог и сценарий', text: 'Добавьте букеты с ценами и соберите диалог в визуальном редакторе.' },
  { n: '03', title: 'AI начинает продавать', text: 'Бот отвечает клиентам, собирает заказ и доводит до оплаты. Вы — получаете заявки.' },
];

const PLANS = [
  { name: 'Старт', price: '0', period: 'на старте', tagline: 'Попробовать без риска',
    perks: ['1 мессенджер-канал', 'AI-агент на Gemini', 'Визуальный редактор', 'До 100 диалогов / мес'], cta: 'Начать бесплатно', highlight: false },
  { name: 'Магазин', price: '7 900', period: '₽ / мес', tagline: 'Для работающей точки',
    perks: ['WhatsApp + Instagram', 'Безлимит диалогов', 'CRM и аналитика', 'Счета и приём оплаты', 'Передача менеджеру'], cta: 'Выбрать тариф', highlight: true },
  { name: 'Сеть', price: 'Договорная', period: '', tagline: 'Несколько точек и бренд',
    perks: ['Мультимагазин', 'Приоритетная поддержка', 'Свой домен и брендинг', 'Интеграции под ключ'], cta: 'Обсудить', highlight: false },
];

const CHAT = [
  { from: 'client', text: 'Здравствуйте! Нужен букет жене на годовщину 🙈' },
  { from: 'bot', text: 'Годовщина — это так трогательно 🤍 Жёны обычно тают от пионов или нежных пудровых роз. Какой бюджет ориентир, чтобы я подобрала идеально?' },
  { from: 'client', text: 'до 10 тысяч' },
  { from: 'bot', text: 'Тогда советую «Нежность» — 25 бело-розовых роз, выглядит дорого и трогательно. Оформим доставку на сегодня?' },
  { from: 'client', text: 'да, давайте' },
  { from: 'bot', text: 'Прекрасно! Счёт на оплату уже отправила 🌸 Доставим в течение 2 часов.' },
];

function ChatDemo() {
  const [shown, setShown] = useState(1);
  useEffect(() => {
    if (shown >= CHAT.length) return;
    const t = setTimeout(() => setShown(s => Math.min(s + 1, CHAT.length)), 1100);
    return () => clearTimeout(t);
  }, [shown]);
  return (
    <div className="lp-phone">
      <div className="lp-phone-top">
        <span className="lp-phone-ava">🌷</span>
        <div>
          <b>Лавка «Весна»</b>
          <small>онлайн · отвечает за секунды</small>
        </div>
        <span className="lp-phone-wa"><IconWhatsapp /></span>
      </div>
      <div className="lp-phone-body">
        {CHAT.slice(0, shown).map((m, i) => (
          <div key={i} className={`lp-bubble ${m.from}`}>{m.text}</div>
        ))}
        {shown < CHAT.length && <div className="lp-bubble bot typing"><span/><span/><span/></div>}
      </div>
    </div>
  );
}

export default function Landing() {
  return (
    <div className="lp">
      <header className="lp-nav">
        <div className="lp-nav-inner">
          <div className="lp-brand">Floral<span>·</span><small>AI</small></div>
          <nav className="lp-nav-links">
            <a href="#features">Возможности</a>
            <a href="#how">Как работает</a>
            <a href="#pricing">Тарифы</a>
          </nav>
          <div className="lp-nav-cta">
            <Link to="/login" className="lp-link">Войти</Link>
            <Link to="/signup" className="btn lp-btn-primary">Создать ателье</Link>
          </div>
        </div>
      </header>

      <section className="lp-hero">
        <div className="lp-hero-text">
          <span className="lp-eyebrow"><IconSparkle /> AI-продажи для цветочных магазинов</span>
          <h1>Ваш магазин продаёт цветы<br/><em>сам</em> — пока вы спите</h1>
          <p className="lp-lead">
            Floral AI — это умный продавец в WhatsApp и Instagram. Он отвечает клиентам как живой
            флорист, собирает заказ и доводит до оплаты. Без операторов, без потерянных заявок.
          </p>
          <div className="lp-hero-actions">
            <Link to="/signup" className="btn lp-btn-primary lp-btn-lg">Попробовать бесплатно</Link>
            <a href="#how" className="btn secondary lp-btn-lg">Как это работает</a>
          </div>
          <div className="lp-hero-trust">
            <span><IconCheck /> Запуск за 1 день</span>
            <span><IconCheck /> Без программистов</span>
            <span><IconCheck /> Бесплатный AI на старте</span>
          </div>
        </div>
        <div className="lp-hero-visual">
          <div className="lp-glow" />
          <ChatDemo />
        </div>
      </section>

      <section className="lp-stats">
        <div className="lp-stat"><b>24/7</b><span>бот на связи</span></div>
        <div className="lp-stat"><b>&lt;5 сек</b><span>скорость ответа</span></div>
        <div className="lp-stat"><b>+38%</b><span>к конверсии в заказ</span></div>
        <div className="lp-stat"><b>0 ₽</b><span>за пропущенные заявки</span></div>
      </section>

      <section className="lp-section" id="features">
        <div className="lp-section-head">
          <span className="lp-eyebrow">Возможности</span>
          <h2>Всё, чтобы продавать больше — в одном месте</h2>
          <p className="lp-sub">От первого «Здравствуйте» до оплаченного счёта и повторной продажи.</p>
        </div>
        <div className="lp-features">
          {FEATURES.map((f, i) => (
            <div className="lp-feature" key={i}>
              <span className="lp-feature-ic"><f.icon /></span>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="lp-section lp-how" id="how">
        <div className="lp-section-head">
          <span className="lp-eyebrow">Как это работает</span>
          <h2>Запуск за три шага</h2>
          <p className="lp-sub">Никакого кода. Справится любой сотрудник магазина.</p>
        </div>
        <div className="lp-steps">
          {STEPS.map((s, i) => (
            <div className="lp-step" key={i}>
              <span className="lp-step-n">{s.n}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="lp-section lp-pricing" id="pricing">
        <div className="lp-section-head">
          <span className="lp-eyebrow">Тарифы</span>
          <h2>Прозрачные цены</h2>
          <p className="lp-sub">Начните бесплатно. Платите, когда почувствуете результат.</p>
        </div>
        <div className="lp-plans">
          {PLANS.map((p, i) => (
            <div className={`lp-plan ${p.highlight ? 'featured' : ''}`} key={i}>
              {p.highlight && <span className="lp-plan-badge">Популярный</span>}
              <div className="lp-plan-name">{p.name}</div>
              <div className="lp-plan-tag">{p.tagline}</div>
              <div className="lp-plan-price"><b>{p.price}</b> <span>{p.period}</span></div>
              <ul>{p.perks.map((perk, j) => <li key={j}><IconCheck /> {perk}</li>)}</ul>
              <Link to="/signup" className={`btn lp-btn-lg ${p.highlight ? 'lp-btn-primary' : 'secondary'}`} style={{width:'100%', justifyContent:'center'}}>{p.cta}</Link>
            </div>
          ))}
        </div>
      </section>

      <section className="lp-cta">
        <div className="lp-cta-card">
          <h2>Дайте магазину продавца, который не устаёт</h2>
          <p>Подключите Floral AI сегодня — и завтра ни одна заявка не останется без ответа.</p>
          <Link to="/signup" className="btn lp-btn-primary lp-btn-lg">Создать ателье бесплатно</Link>
        </div>
      </section>

      <footer className="lp-footer">
        <div className="lp-brand">Floral<span>·</span><small>AI</small></div>
        <div className="lp-footer-links">
          <a href="#features">Возможности</a>
          <a href="#pricing">Тарифы</a>
          <Link to="/login">Войти</Link>
        </div>
        <div className="lp-footer-copy">© {new Date().getFullYear()} Floral AI · продажи цветов на автопилоте</div>
      </footer>
    </div>
  );
}
