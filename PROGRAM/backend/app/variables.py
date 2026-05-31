"""Валидация/нормализация значений переменных по имени.

Все нормализованные значения пригодны как для хранения, так и для
повторного показа клиенту через `humanize_variable` (например, ISO-дата
'2025-12-25' → '25 декабря', чтобы бот не выглядел роботом).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

_PHONE_RE = re.compile(r"[\d\+\-\(\)\s]{7,}")
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# Слова, которые точно НЕ являются ответом по существу.
# Используются и в save_slot-валидаторе агента, и в эвристиках.
NON_ANSWER_PHRASES = {
    "не знаю", "хз", "без понятия", "не помню", "сам выбери", "сами выберите",
    "выбирай ты", "посоветуй", "посоветуйте", "что посоветуете", "на ваш вкус",
    "не определился", "не определилась", "пока не знаю", "затрудняюсь",
    "вы решите", "помогите выбрать", "не могу решить",
}

_RU_MONTHS_GEN = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
    7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}
_RU_WEEKDAYS = {
    "понедельник": 0, "понедел": 0, "пн": 0,
    "вторник": 1, "вторн": 1, "вт": 1,
    "среду": 2, "среда": 2, "среде": 2, "ср": 2,
    "четверг": 3, "чт": 3,
    "пятницу": 4, "пятница": 4, "пятниц": 4, "пт": 4,
    "субботу": 5, "суббота": 5, "субб": 5, "сб": 5,
    "воскресенье": 6, "воскресен": 6, "вс": 6,
}
_RU_MONTHS_BY_NAME = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}


def _clean_phone(text: str) -> str:
    digits = re.sub(r"\D", "", text or "")
    # нормализуем 8… → +7…
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) >= 10:
        return "+" + digits if not digits.startswith("+") else digits
    return ""


def _next_weekday(today: date, target_idx: int) -> date:
    delta = (target_idx - today.weekday()) % 7
    if delta == 0:
        delta = 7  # «в пятницу» сегодня = следующая пятница
    return today + timedelta(days=delta)


def _parse_date(text: str) -> str:
    if not text:
        return ""
    s = text.strip().lower()
    # Числовые форматы
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d-%m-%Y", "%d %m %Y", "%d.%m", "%d/%m"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt in ("%d.%m", "%d/%m"):
                today = datetime.now()
                dt = dt.replace(year=today.year)
                # если дата уже прошла в этом году — берём следующий год
                if dt.date() < today.date():
                    dt = dt.replace(year=today.year + 1)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    today = datetime.now().date()

    # Относительные слова — порядок важен: «послезавтра» содержит «завтра»!
    if "послезавтра" in s:
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    if "завтра" in s:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if "сегодня" in s:
        return today.strftime("%Y-%m-%d")

    # Текстовая форма «25 декабря», «25 декабря 2026»
    m = re.search(r"(\d{1,2})\s+([а-яё]+)(?:\s+(\d{4}))?", s)
    if m:
        day = int(m.group(1))
        month_word = m.group(2)
        year = int(m.group(3)) if m.group(3) else today.year
        for prefix, month in _RU_MONTHS_BY_NAME.items():
            if month_word.startswith(prefix):
                try:
                    dt = date(year, month, day)
                    if not m.group(3) and dt < today:
                        dt = date(year + 1, month, day)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    return ""

    # «в пятницу», «в субботу», «к понедельнику»
    m = re.search(r"(?:^|\b)(?:в |к |на |этой |следующ\w+ |на этой |на следующ\w+ )?([а-яё]+)", s)
    if m:
        for word, idx in _RU_WEEKDAYS.items():
            if m.group(1).startswith(word):
                return _next_weekday(today, idx).strftime("%Y-%m-%d")

    return ""


def _humanize_date(iso: str) -> str:
    """ISO-дата → «25 декабря» или «завтра, 25 декабря» если близко."""
    try:
        dt = datetime.strptime(iso, "%Y-%m-%d").date()
    except Exception:
        return iso
    today = datetime.now().date()
    delta = (dt - today).days
    base = f"{dt.day} {_RU_MONTHS_GEN[dt.month]}"
    if delta == 0:
        return f"сегодня, {base}"
    if delta == 1:
        return f"завтра, {base}"
    if delta == 2:
        return f"послезавтра, {base}"
    if 0 < delta <= 6:
        wd = ["в понедельник", "во вторник", "в среду", "в четверг", "в пятницу", "в субботу", "в воскресенье"][dt.weekday()]
        return f"{wd}, {base}"
    if dt.year != today.year:
        return f"{base} {dt.year}"
    return base


def _normalize_name(text: str) -> str:
    """«меня зовут Алексей» → «Алексей»; «алексей петров» → «Алексей Петров»."""
    s = (text or "").strip()
    # убираем вводные обороты
    s = re.sub(
        r"^(меня\s+зовут|зовут|это|я|зови|зовите|обращайтесь|можно)\s+",
        "", s, flags=re.IGNORECASE,
    ).strip(" ,.!:")
    # выкидываем явный мусор после имени
    s = re.split(r"[,;.\n]", s, maxsplit=1)[0].strip()
    # тайтл-кейс по словам
    parts = [p for p in s.split() if p]
    titled = []
    for p in parts:
        if p[0].isalpha():
            titled.append(p[0].upper() + p[1:].lower() if len(p) > 1 else p.upper())
        else:
            titled.append(p)
    return " ".join(titled)


def is_non_answer(text: str) -> bool:
    """Клиент явно отказался отвечать или попросил магазин выбрать сам."""
    low = (text or "").strip().lower()
    if not low:
        return True
    return any(p in low for p in NON_ANSWER_PHRASES)


def validate_variable(name: str, value: str) -> tuple[bool, str, str]:
    """
    Возвращает (ok, normalized_value, hint).
    hint — подсказка для клиента, если значение невалидно.
    Для неизвестных имён — считаем валидным, если непусто.
    """
    if value is None:
        return False, "", "Пожалуйста, уточните ответ."
    v = str(value).strip()
    n = (name or "").lower()

    if not v:
        return False, "", "Пожалуйста, ответьте на вопрос."

    if n in {"phone", "telephone", "tel", "mobile", "телефон"}:
        p = _clean_phone(v)
        if p:
            return True, p, ""
        return False, "", "Пожалуйста, пришлите номер телефона, например +7 999 123-45-67."

    if n in {"email", "mail", "почта"}:
        if _EMAIL_RE.search(v):
            return True, v, ""
        return False, "", "Пришлите, пожалуйста, e-mail в формате name@domain.ru."

    if n in {"date", "delivery_date", "дата"}:
        d = _parse_date(v)
        if d:
            return True, d, ""
        return False, "", "Дата не распознана. Напишите, например, «завтра», «в пятницу» или «15.06.2025»."

    if n in {"name", "имя"}:
        cleaned = _normalize_name(v)
        if 1 < len(cleaned) < 64 and any(c.isalpha() for c in cleaned):
            return True, cleaned, ""
        return False, "", "Как к вам обращаться? Напишите, пожалуйста, имя."

    if n in {"address", "адрес"}:
        # принимаем «самовывоз», «заберу сам», иначе требуем минимальную длину или явные маркеры
        low = v.lower()
        if any(w in low for w in ("самовывоз", "заберу сам", "заберу из магазин", "приду сам", "сам забер")):
            return True, "Самовывоз", ""
        if len(v) >= 6:
            return True, v, ""
        return False, "", "Уточните адрес (город, улица, дом) или напишите «самовывоз»."

    # default: непустой текст считаем ок
    return True, v, ""


def humanize_variable(name: str, value: str) -> str:
    """Преобразует нормализованное значение в человеческое для показа клиенту в reply.

    delivery_date '2025-12-25' → '25 декабря'.
    Остальные слоты возвращаются как есть.
    """
    n = (name or "").lower()
    v = str(value or "").strip()
    if not v:
        return v
    if n in {"date", "delivery_date", "дата"}:
        return _humanize_date(v)
    return v
