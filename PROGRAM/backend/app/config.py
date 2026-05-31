import hashlib
import hmac
import time

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Список значений, которые мы считаем "не задано / placeholder".
_DEFAULT_JWT_SECRETS = {
    "change_this_in_prod_please_min_32_chars_long_secret",
    "change_me",
    "change_me_min_32_chars_random",
    "",
}
_DEFAULT_BRIDGE_SECRETS = {
    "change_me",
    "change_me_wa_bridge_random",
    "",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # AI provider: free|anthropic|openai|gemini. Default — gemini: бесплатный ключ
    # в Google AI Studio (https://aistudio.google.com/apikey), щедрые лимиты и
    # отличное качество на русском. Если ключ не задан (ни у магазина, ни в env) —
    # _resolve_creds мягко откатывается на провайдер `free` (Pollinations.ai),
    # чтобы бот работал «из коробки» без настройки.
    ai_provider: str = "gemini"
    gemini_api_key: str = ""
    # gemini-2.5-flash — отличное качество ответов на русском. Для большего объёма
    # запросов в день можно поставить gemini-2.5-flash-lite в настройках магазина.
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"
    # Pollinations.ai — бесплатный текстовый API (https://text.pollinations.ai),
    # OpenAI-совместимый. Ключ не нужен.
    free_base_url: str = "https://text.pollinations.ai/openai"
    free_model: str = "openai-large"
    ai_timeout_seconds: int = 45
    ai_max_retries: int = 4
    ai_history_window: int = 20

    # WhatsApp bridge
    wa_bridge_url: str = "http://localhost:3001"
    wa_bridge_secret: str = "change_me"
    # Допустимое расхождение часов между WA-мостом и backend, секунд.
    wa_webhook_max_skew: int = 300

    # Instagram fallback (предпочтительно настраивать в UI)
    ig_username: str = ""
    ig_password: str = ""

    # DB
    database_url: str = "sqlite:///./data.db"

    # JWT
    jwt_secret: str = "change_this_in_prod_please_min_32_chars_long_secret"
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 60
    jwt_refresh_days: int = 30

    # Шифрование чувствительных полей в БД (Fernet key, urlsafe base64)
    # Сгенерировать: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secret_encryption_key: str = ""

    # Отдельный ключ для подписи pay-ссылок. Если пусто — деривируется из JWT_SECRET (backward compat).
    pay_signing_key_raw: str = Field(default="", alias="PAY_SIGNING_KEY")
    # TTL pay-ссылки, секунд (по умолчанию 7 суток).
    pay_link_ttl_seconds: int = 7 * 24 * 3600

    # CORS: разделять запятыми. "*" допустим только в dev.
    cors_origins_raw: str = Field(default="http://localhost:5173,http://localhost:8000", alias="CORS_ORIGINS")

    @property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.cors_origins_raw.split(",") if x.strip()]

    # Базовый URL публичной части (ссылки на счета).
    public_base_url: str = "http://localhost:8000"
    default_currency: str = "RUB"

    # Rate limits
    rate_limit_login: str = "10/minute"
    rate_limit_signup: str = "5/hour"
    rate_limit_sim: str = "60/minute"
    rate_limit_wa_connect: str = "10/minute"
    rate_limit_pay_confirm: str = "20/minute"

    # Окружение (dev|prod) — включает/выключает доп. проверки
    env: str = "dev"

    # Redis — общий для rate-limit и advisory-locks. Пусто = используем in-memory/in-process
    # fallback (ОК для dev/single-worker; для prod с --workers > 1 обязательно задайте URL).
    redis_url: str = ""

    # ---------- production safety ----------
    def validate_for_env(self) -> None:
        """Падаем на старте, если в prod не сменены критичные секреты."""
        if self.env != "prod":
            return
        problems: list[str] = []
        if self.jwt_secret in _DEFAULT_JWT_SECRETS or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET")
        if self.wa_bridge_secret in _DEFAULT_BRIDGE_SECRETS or len(self.wa_bridge_secret) < 16:
            problems.append("WA_BRIDGE_SECRET")
        if not self.secret_encryption_key:
            problems.append("SECRET_ENCRYPTION_KEY")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS contains '*'")
        if problems:
            raise RuntimeError(
                "Insecure config in ENV=prod: " + ", ".join(problems)
                + ". Сгенерируйте сильные значения перед запуском."
            )

    # ---------- payment link signing ----------
    @property
    def pay_signing_key(self) -> bytes:
        """Ключ для подписи pay-ссылок. Отдельный от JWT — если задан PAY_SIGNING_KEY."""
        if self.pay_signing_key_raw:
            return hashlib.sha256(self.pay_signing_key_raw.encode()).digest()
        # Backward compat: деривация из jwt_secret. Не используйте в проде.
        return hashlib.sha256((self.jwt_secret + ":pay-link-v1").encode()).digest()

    def sign_pay_token(self, order_id: int, shop_id: int, exp_ts: int | None = None) -> str:
        """Формат: <exp_hex>.<sig16>. exp_ts=0/None — бессрочный (для обратной совместимости в тестах)."""
        if exp_ts is None:
            exp_ts = int(time.time()) + self.pay_link_ttl_seconds
        msg = f"{shop_id}:{order_id}:{exp_ts}".encode()
        sig = hmac.new(self.pay_signing_key, msg, hashlib.sha256).hexdigest()[:32]
        return f"{exp_ts:x}.{sig}"

    def verify_pay_token(self, order_id: int, shop_id: int, token: str) -> bool:
        if not token:
            return False
        # Новый формат: "<exp_hex>.<sig>"
        if "." in token:
            try:
                exp_hex, sig = token.split(".", 1)
                exp_ts = int(exp_hex, 16)
            except Exception:
                return False
            if exp_ts and exp_ts < int(time.time()):
                return False
            msg = f"{shop_id}:{order_id}:{exp_ts}".encode()
            expected = hmac.new(self.pay_signing_key, msg, hashlib.sha256).hexdigest()[:32]
            return hmac.compare_digest(expected, sig)
        # Legacy: 32-hex без срока годности. Принимаем только в dev/test.
        if self.env == "prod":
            return False
        legacy_msg = f"{shop_id}:{order_id}".encode()
        legacy_expected = hmac.new(self.pay_signing_key, legacy_msg, hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(legacy_expected, token)


settings = Settings()
