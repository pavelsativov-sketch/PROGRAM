"""Базовая настройка логирования: JSON в prod, plain в dev."""
import logging
import sys

from .config import settings


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # уже настроено
    handler = logging.StreamHandler(sys.stdout)
    if settings.env == "prod":
        try:
            from pythonjsonlogger import jsonlogger
            fmt = jsonlogger.JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s"
            )
            handler.setFormatter(fmt)
        except Exception:
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # sqlalchemy шумный
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
