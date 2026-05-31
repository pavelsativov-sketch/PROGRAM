from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


# ---- Auth ----
class SignupIn(BaseModel):
    email: EmailStr
    password: str
    name: str = "My Flower Shop"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ShopOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    currency: str
    timezone: str = "UTC"
    ai_provider: str
    ai_model: str
    ig_username: str
    ig_connected: bool
    wa_connected: bool
    wa_phone: str
    kaspi_phone: str = ""
    kaspi_name: str = ""
    kaspi_qr_url: str = ""
    payment_instructions: str = ""
    business_hours: dict | None = None
    # Не возвращаем сам token наружу — только флаг наличия
    tg_chat_id: str = ""
    tg_configured: bool = False
    bot_enabled: bool = True
    daily_summary_hour: int = 21
    followup_enabled: bool = True

    model_config = ConfigDict(from_attributes=True)


class ShopSettingsIn(BaseModel):
    name: str | None = None
    currency: str | None = None
    timezone: str | None = None
    ai_provider: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None
    kaspi_phone: str | None = None
    kaspi_name: str | None = None
    kaspi_qr_url: str | None = None
    payment_instructions: str | None = None
    business_hours: dict | None = None
    tg_bot_token: str | None = None
    tg_chat_id: str | None = None
    bot_enabled: bool | None = None
    daily_summary_hour: int | None = None
    followup_enabled: bool | None = None


# ---- Flows ----
class FlowBase(BaseModel):
    name: str
    description: str = ""
    is_active: bool = True
    graph: dict = {}


class FlowCreate(FlowBase):
    pass


class FlowOut(FlowBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---- Products ----
class ProductIn(BaseModel):
    name: str
    category: str = "Bouquets"
    description: str = ""
    price: float = 0.0
    image_url: str = ""
    available_today: bool = True
    is_active: bool = True


class ProductOut(ProductIn):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ---- Orders ----
class OrderOut(BaseModel):
    id: int
    conversation_id: int | None
    customer_id: int | None
    items: list
    total: float
    status: str
    payment_link: str
    details: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---- Conversations ----
class ConversationOut(BaseModel):
    id: int
    customer_id: int | None
    flow_id: int | None
    current_node_id: str
    variables: dict
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SimMessageIn(BaseModel):
    conversation_id: int | None = None
    flow_id: int | None = None
    external_id: str = "sim-user"
    text: str


class ManagerReplyIn(BaseModel):
    text: str
