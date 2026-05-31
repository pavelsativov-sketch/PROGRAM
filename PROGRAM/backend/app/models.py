from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base, EncryptedString


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Shop(Base):
    """Магазин = арендатор SaaS."""
    __tablename__ = "shops"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False, default="My Flower Shop")
    currency = Column(String(8), default="RUB")
    timezone = Column(String(64), default="Europe/Moscow")
    # AI настройки per-shop (опционально, иначе глобальные из env)
    ai_provider = Column(String(16), default="")          # gemini|openai|""
    ai_api_key = Column(EncryptedString(1024), default="")
    ai_model = Column(String(64), default="")
    # Состояние каналов (зашифрованные сессии храним во внешних файлах)
    ig_username = Column(String(255), default="")
    ig_proxy = Column(EncryptedString(512), default="")  # http(s)://user:pass@host:port — обходит IP-блок IG
    ig_connected = Column(Boolean, default=False)
    # Карта thread_id → last_message_id для IG-поллера (чтобы после рестарта не дублировать сообщения).
    ig_last_seen = Column(JSON, default=dict)
    wa_connected = Column(Boolean, default=False)
    wa_phone = Column(String(32), default="")
    kaspi_phone = Column(String(32), default="")
    kaspi_name = Column(String(255), default="")
    kaspi_qr_url = Column(String(512), default="")
    payment_instructions = Column(Text, default="")
    # График работы магазина (JSON): {"mon":{"open":"09:00","close":"21:00"}, ...,
    # "sun":null} — null/отсутствие = выходной.
    business_hours = Column(JSON, default=dict)
    # Telegram-нотификатор: владелец магазина создаёт бота через @BotFather,
    # пишет ему первое сообщение, чтобы получить chat_id, и кладёт оба поля сюда.
    # Ключ зашифрован Fernet.
    tg_bot_token = Column(EncryptedString(256), default="")
    tg_chat_id = Column(String(64), default="")
    # Бот включён? Если False — входящие не обрабатываются AI, а сразу уходят
    # менеджеру (handoff). Используется для алертов «бот отключён».
    bot_enabled = Column(Boolean, default=True)
    # Час (0-23) в таймзоне магазина, когда слать ежедневную сводку в Telegram.
    daily_summary_hour = Column(Integer, default=21)
    # Дожимать ли брошенные диалоги авто-сообщением в канал.
    followup_enabled = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    # Все JWT, выданные ДО этого момента — невалидны. Обновляется при login и смене пароля.
    tokens_valid_after = Column(DateTime(timezone=True), default=_utcnow)

    flows = relationship("Flow", back_populates="shop", cascade="all, delete-orphan")

    @property
    def tg_configured(self) -> bool:
        """Удобный флаг для UI: настроены ли token+chat_id для Telegram-уведомлений."""
        return bool((self.tg_bot_token or "").strip() and (self.tg_chat_id or "").strip())


class Flow(Base):
    __tablename__ = "flows"
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    graph = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    shop = relationship("Shop", back_populates="flows")

    __table_args__ = (Index("ix_flow_shop_active", "shop_id", "is_active"),)


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=False)
    channel = Column(String(32))
    external_id = Column(String(128), index=True)
    name = Column(String(255), default="")
    # CRM-поля: теги-маркеры (VIP, корпоратив, жалобщик и т.п.) и свободные заметки менеджера.
    tags = Column(JSON, default=list)
    notes = Column(Text, default="")
    # Важные даты клиента для напоминаний о повторных продажах.
    # Список словарей: [{"label": "День рождения мамы", "date": "2026-03-08", "recurring": true}].
    important_dates = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_customer_shop_channel_ext", "shop_id", "channel", "external_id", unique=True),)


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    flow_id = Column(Integer, ForeignKey("flows.id"))
    current_node_id = Column(String(64), default="")
    variables = Column(JSON, default=dict)
    status = Column(String(32), default="active")
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    customer = relationship("Customer")
    flow = relationship("Flow")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )

    __table_args__ = (
        Index("ix_conv_shop_status", "shop_id", "status"),
        Index("ix_conv_shop_updated", "shop_id", "updated_at"),
    )


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    role = Column(String(16))
    text = Column(Text, default="")
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (Index("ix_msg_conv_id", "conversation_id", "id"),)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=False)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    items = Column(JSON, default=list)
    total = Column(Float, default=0.0)
    status = Column(String(32), default="new")
    payment_link = Column(String(512), default="")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (Index("ix_order_shop_status", "shop_id", "status"),)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(128), default="Bouquets")
    description = Column(Text, default="")
    price = Column(Float, default=0.0)
    image_url = Column(String(512), default="")
    available_today = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)


class RevokedToken(Base):
    """Список отозванных JWT по jti — проверяется на каждом запросе."""
    __tablename__ = "revoked_tokens"
    jti = Column(String(64), primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    revoked_at = Column(DateTime(timezone=True), default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)


class IncomingMessage(Base):
    """Inbox: входящее сообщение из канала сохраняется СИНХРОННО до AI-обработки.

    Это защищает от потери сообщения, если backend упадёт между ACK webhook'а и
    `handle_incoming`. Scheduler-job (см. main.py) подбирает unprocessed-записи и
    повторно отправляет их в диспетчер.
    """
    __tablename__ = "incoming_messages"
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=False)
    channel = Column(String(32), nullable=False)            # whatsapp|instagram|sim
    external_id = Column(String(128), nullable=False)       # клиент в канале
    customer_name = Column(String(255), default="")
    text = Column(Text, default="")
    status = Column(String(16), default="pending", index=True)  # pending|processed|failed
    attempts = Column(Integer, default=0)
    last_error = Column(String(512), default="")
    received_at = Column(DateTime(timezone=True), default=_utcnow)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_inbox_status_received", "status", "received_at"),
        Index("ix_inbox_shop_status", "shop_id", "status"),
    )


class Notification(Base):
    """Уведомление магазину: центр уведомлений в приложении + фан-аут в Telegram/пуш.

    Типы (``type``): handoff | bot_down | bot_idle | bot_disabled | ai_error |
    new_order | order_paid | reminder | daily_summary | followup.
    ``dedup_key`` + временное окно защищают от спама повторными алертами.
    """
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=False)
    type = Column(String(32), nullable=False)
    severity = Column(String(16), default="info")     # info | warning | critical
    title = Column(String(255), nullable=False)
    body = Column(Text, default="")
    link = Column(String(255), default="")            # in-app ссылка, напр. /conversations?filter=handoff
    meta = Column(JSON, default=dict)
    dedup_key = Column(String(128), default="", index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_notif_shop_created", "shop_id", "created_at"),
        Index("ix_notif_shop_read", "shop_id", "read_at"),
    )


class AuditLog(Base):
    """Лог значимых действий: логин/логаут, смена настроек, подключение каналов."""
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=True)
    action = Column(String(64), nullable=False)
    ip = Column(String(64), default="")
    user_agent = Column(String(255), default="")
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_audit_shop_created", "shop_id", "created_at"),)
