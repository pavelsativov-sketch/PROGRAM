"""График работы магазина.

Формат `Shop.business_hours`:
    {
      "mon": {"open": "09:00", "close": "21:00"},
      "tue": {"open": "09:00", "close": "21:00"},
      ...
      "sun": null   # или отсутствует — выходной
    }

Если поле пустое/none — считаем магазин круглосуточным (поведение по умолчанию,
как было до этой фичи).
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_RU_GEN = {  # для предложений вроде «откроемся в понедельник в 9:00»
    "mon": "понедельник", "tue": "вторник", "wed": "среду", "thu": "четверг",
    "fri": "пятницу", "sat": "субботу", "sun": "воскресенье",
}


def _shop_tz(shop) -> ZoneInfo:
    try:
        return ZoneInfo(getattr(shop, "timezone", "") or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _parse_hm(s: str) -> time | None:
    try:
        h, m = s.split(":", 1)
        return time(int(h), int(m))
    except Exception:
        return None


def is_open_now(shop, now: datetime | None = None) -> bool:
    """True, если магазин сейчас открыт. Если business_hours пуст — всегда True."""
    bh = getattr(shop, "business_hours", None) or {}
    if not bh:
        return True
    tz = _shop_tz(shop)
    cur = (now or datetime.now(tz)).astimezone(tz)
    key = DAY_KEYS[cur.weekday()]
    day = bh.get(key)
    if not day:
        return False
    open_t = _parse_hm(str(day.get("open") or ""))
    close_t = _parse_hm(str(day.get("close") or ""))
    if not open_t or not close_t:
        return True  # некорректная конфигурация — лучше быть открытым, чем потерять клиента
    cur_t = cur.time()
    if open_t <= close_t:
        return open_t <= cur_t < close_t
    # окно через полночь (22:00 → 02:00)
    return cur_t >= open_t or cur_t < close_t


def next_open(shop, now: datetime | None = None) -> tuple[str, str] | None:
    """Возвращает (день_ru_genitive, время_открытия 'HH:MM') ближайшего открытия.
    None — магазин круглосуточный или график не задан."""
    bh = getattr(shop, "business_hours", None) or {}
    if not bh:
        return None
    tz = _shop_tz(shop)
    cur = (now or datetime.now(tz)).astimezone(tz)
    for offset in range(8):  # сегодня + 7 дней
        idx = (cur.weekday() + offset) % 7
        key = DAY_KEYS[idx]
        day = bh.get(key)
        if not day:
            continue
        open_t = _parse_hm(str(day.get("open") or ""))
        if not open_t:
            continue
        if offset == 0:
            cur_t = cur.time()
            close_t = _parse_hm(str(day.get("close") or "")) or time(23, 59)
            if open_t <= close_t and open_t <= cur_t < close_t:
                return None  # уже открыто
            if open_t <= close_t and cur_t >= open_t:
                continue  # сегодня уже закрылись
        return DAY_RU_GEN[key], open_t.strftime("%H:%M")
    return None


def closed_message(shop) -> str:
    """Готовое сообщение про «мы закрыты, но примем заказ»."""
    nxt = next_open(shop)
    if nxt is None:
        return ""
    day, t = nxt
    return (
        f"Мы сейчас не работаем, но я приму ваш заказ — "
        f"курьер выедет, как только откроемся ({day} в {t})."
    )
