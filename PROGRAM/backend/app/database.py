"""DB connection + прозрачное шифрование чувствительных полей (Fernet)."""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import settings

log = logging.getLogger(__name__)


# ---------- Fernet ----------
_fernet: Fernet | None = None


def _get_fernet() -> Fernet | None:
    global _fernet
    if _fernet is not None:
        return _fernet
    key = (settings.secret_encryption_key or "").strip()
    if not key:
        if settings.env == "prod":
            raise RuntimeError(
                "SECRET_ENCRYPTION_KEY is required in prod. "
                "Generate: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        log.warning("SECRET_ENCRYPTION_KEY не задан — чувствительные поля хранятся в открытом виде (dev).")
        return None
    try:
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        raise RuntimeError(f"Invalid SECRET_ENCRYPTION_KEY: {e}") from e
    return _fernet


_ENC_PREFIX = "enc:v1:"


class EncryptedString(TypeDecorator):
    """Строка, шифрующаяся Fernet. Обратно совместимо со значениями в открытом виде."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return value
        f = _get_fernet()
        if f is None:
            return value  # dev без ключа — сохраняем как есть
        token = f.encrypt(value.encode("utf-8")).decode("ascii")
        return _ENC_PREFIX + token

    def process_result_value(self, value, dialect):
        if value is None or value == "":
            return value
        if not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
            return value  # backward compat — старые plaintext-записи
        f = _get_fernet()
        if f is None:
            return value  # не сможем расшифровать без ключа — возвращаем как есть, слой выше должен обработать
        try:
            return f.decrypt(value[len(_ENC_PREFIX):].encode("ascii")).decode("utf-8")
        except InvalidToken:
            log.error("EncryptedString: invalid token (wrong SECRET_ENCRYPTION_KEY?)")
            return ""


# ---------- Engine / Session ----------
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
