"""AI layer: supports Anthropic (Claude), OpenAI and Gemini. Per-shop keys или fallback в env."""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import settings

log = logging.getLogger(__name__)


class _AIRetryable(Exception):
    """Ошибка, на которую имеет смысл ретраить."""


_VALID_PROVIDERS = {"free", "anthropic", "openai", "gemini"}


def _resolve_creds(shop) -> tuple[str, str, str]:
    """Возвращает (provider, api_key, model) — сначала настройки магазина, потом env.

    Для провайдера ``free`` ключ не нужен и всегда возвращается пустой —
    но _has_creds() считает его валидным.
    """
    provider = (shop and shop.ai_provider) or settings.ai_provider or "free"
    if provider not in _VALID_PROVIDERS:
        provider = "free"
    if provider == "free":
        model = (shop and shop.ai_model) or settings.free_model
        return "free", "", model or "openai"
    if provider == "openai":
        key = (shop and shop.ai_api_key) or settings.openai_api_key
        model = (shop and shop.ai_model) or settings.openai_model
    elif provider == "gemini":
        key = (shop and shop.ai_api_key) or settings.gemini_api_key
        model = (shop and shop.ai_model) or settings.gemini_model
    else:  # anthropic
        provider = "anthropic"
        key = (shop and shop.ai_api_key) or settings.anthropic_api_key
        model = (shop and shop.ai_model) or settings.anthropic_model
    return provider, key or "", model or ""


def _has_creds(provider: str, key: str) -> bool:
    """free работает без ключа; остальным нужен key."""
    return provider == "free" or bool(key)


def _free_chat(messages: list[dict], *, json_mode: bool = False, temperature: float = 0.6) -> str:
    """Бесплатный публичный OpenAI-совместимый эндпоинт (Pollinations.ai).

    Кидает _AIRetryable при сетевых/5xx ошибках, чтобы tenacity ретраил.
    """
    url = settings.free_base_url.rstrip("/") + "/chat/completions"
    payload: dict = {
        "model": settings.free_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1024,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        with httpx.Client(timeout=settings.ai_timeout_seconds) as c:
            r = c.post(url, json=payload, headers={"Content-Type": "application/json"})
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise _AIRetryable(f"free transport: {e}")
    if r.status_code >= 500 or r.status_code == 429:
        raise _AIRetryable(f"free http {r.status_code}: {r.text[:200]}")
    if r.status_code >= 400:
        # для 4xx (не 429) можно попробовать упрощённый формат
        try:
            with httpx.Client(timeout=settings.ai_timeout_seconds) as c:
                r2 = c.post(
                    settings.free_base_url.rstrip("/").removesuffix("/openai") + "/",
                    json={"messages": messages, "model": settings.free_model, "jsonMode": json_mode},
                )
            if r2.status_code < 300:
                return (r2.text or "").strip()
        except Exception:
            pass
        raise _AIRetryable(f"free http {r.status_code}")
    try:
        data = r.json()
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        raise _AIRetryable(f"free parse: {e}")


def _anthropic_history(history: list[dict]) -> list[dict]:
    """Anthropic требует чередование user/assistant. Склеиваем подряд идущие одной роли."""
    out: list[dict] = []
    for h in history:
        role = "user" if h.get("role") == "user" else "assistant"
        content = h.get("content") or ""
        if not content:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n" + content
        else:
            out.append({"role": role, "content": content})
    return out


def _window(history: list[dict]) -> list[dict]:
    n = max(4, settings.ai_history_window)
    return history[-n:]


def _retry(fn):
    return retry(
        stop=stop_after_attempt(max(1, settings.ai_max_retries + 1)),
        wait=wait_exponential(multiplier=0.5, max=5),
        retry=retry_if_exception_type((_AIRetryable, httpx.TimeoutException, httpx.TransportError)),
        reraise=True,
    )(fn)


def ai_reply(shop, system: str, history: list[dict], user_text: str) -> str:
    provider, key, model = _resolve_creds(shop)
    if not _has_creds(provider, key):
        return f"(AI ключ не задан в настройках магазина) Вы написали: {user_text}"

    @_retry
    def _call() -> str:
        if provider == "free":
            msgs = [{"role": "system", "content": system}] + _window(history) + [{"role": "user", "content": user_text}]
            return _free_chat(msgs, temperature=0.6)
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=key, timeout=settings.ai_timeout_seconds)
            msgs = _anthropic_history(_window(history)) + [{"role": "user", "content": user_text}]
            try:
                r = client.messages.create(
                    model=model, system=system, messages=msgs,
                    max_tokens=1024, temperature=0.6,
                )
                parts = [b.text for b in (r.content or []) if getattr(b, "type", "") == "text"]
                return ("\n".join(parts)).strip()
            except (anthropic.APITimeoutError, anthropic.APIConnectionError, anthropic.RateLimitError) as e:
                raise _AIRetryable(str(e))
            except anthropic.APIStatusError as e:
                if 500 <= getattr(e, "status_code", 0) < 600:
                    raise _AIRetryable(str(e))
                raise
        if provider == "openai":
            from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError
            client = OpenAI(api_key=key, timeout=settings.ai_timeout_seconds)
            msgs = [{"role": "system", "content": system}] + _window(history) + [{"role": "user", "content": user_text}]
            try:
                r = client.chat.completions.create(model=model, messages=msgs, temperature=0.6)
                return (r.choices[0].message.content or "").strip()
            except (APITimeoutError, APIConnectionError, RateLimitError) as e:
                raise _AIRetryable(str(e))
            except APIError as e:
                if 500 <= getattr(e, "status_code", 0) < 600:
                    raise _AIRetryable(str(e))
                raise
        # gemini
        import google.generativeai as genai
        from google.api_core.exceptions import (
            DeadlineExceeded,
            InternalServerError,
            ResourceExhausted,
            ServiceUnavailable,
        )
        genai.configure(api_key=key)
        m = genai.GenerativeModel(model_name=model, system_instruction=system)
        gem_hist = [
            {"role": "user" if x["role"] == "user" else "model", "parts": [x["content"]]}
            for x in _window(history)
        ]
        try:
            chat = m.start_chat(history=gem_hist)
            r = chat.send_message(
                user_text,
                request_options={"timeout": settings.ai_timeout_seconds},
            )
            return (r.text or "").strip()
        except (DeadlineExceeded, ResourceExhausted, ServiceUnavailable, InternalServerError) as e:
            raise _AIRetryable(str(e))

    try:
        return _call()
    except _AIRetryable as e:
        log.warning("AI call failed after retries: %s", e)
        return "AI временно недоступен, попробуйте позже."
    except Exception:
        log.exception("AI call failed (non-retryable)")
        return "Извините, сейчас не могу ответить. Уточню у менеджера и вернусь."


def ai_extract(shop, prompt: str, user_text: str) -> str:
    provider, key, model = _resolve_creds(shop)
    if not _has_creds(provider, key):
        return user_text.strip()
    sys = "You extract data. Return ONLY the extracted value, no explanations. Empty string if nothing found."
    try:
        if provider == "free":
            return _free_chat(
                [{"role": "system", "content": sys},
                 {"role": "user", "content": f"Task: {prompt}\nMessage: {user_text}"}],
                temperature=0,
            )
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=key, timeout=settings.ai_timeout_seconds)
            r = client.messages.create(
                model=model, system=sys, max_tokens=256, temperature=0,
                messages=[{"role": "user", "content": f"Task: {prompt}\nMessage: {user_text}"}],
            )
            parts = [b.text for b in (r.content or []) if getattr(b, "type", "") == "text"]
            return ("\n".join(parts)).strip()
        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=key, timeout=settings.ai_timeout_seconds)
            r = client.chat.completions.create(
                model=model, temperature=0,
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": f"Task: {prompt}\nMessage: {user_text}"},
                ],
            )
            return (r.choices[0].message.content or "").strip()
        import google.generativeai as genai
        genai.configure(api_key=key)
        m = genai.GenerativeModel(model_name=model, system_instruction=sys)
        r = m.generate_content(
            f"Task: {prompt}\nClient message: {user_text}",
            request_options={"timeout": settings.ai_timeout_seconds},
        )
        return (r.text or "").strip()
    except Exception as e:
        log.warning("ai_extract failed: %s", e)
        return user_text.strip()


# ---------- Intent classification ----------

VALID_INTENTS = {"answer", "question", "switch_catalog", "handoff", "refuse", "off_topic"}


def _heuristic_intent(user_text: str) -> dict:
    """Fallback без AI — грубые эвристики. Лучше, чем слепо писать всё в переменную."""
    t = (user_text or "").strip()
    low = t.lower()
    catalog_words = ("другой", "друго", "другие", "ещё", "еще", "есть ли", "какие",
                     "покажи", "варианты", "выбор", "каталог", "меню", "ассортимент")
    # Только явные фразы — не одиночные слова «менеджер»/«человек», иначе любой контекст триггерит handoff.
    handoff_words = (
        "позови оператор", "позовите оператор", "хочу оператор", "нужен оператор", "дайте оператор",
        "позови менеджер", "позовите менеджер", "хочу менеджер", "нужен менеджер", "дайте менеджер",
        "соедините с оператор", "соедините с менеджер",
        "живой человек", "позовите человека", "хочу человека", "сотрудника позов",
    )
    refuse_words = ("не хочу говорить", "отказываюсь", "не буду отвечать", "не скажу", "позже")
    if any(w in low for w in handoff_words):
        return {"intent": "handoff", "value": "", "reply": "", "valid": False}
    if any(w in low for w in catalog_words):
        return {"intent": "switch_catalog", "value": "", "reply": "", "valid": False}
    if any(w in low for w in refuse_words):
        return {"intent": "refuse", "value": "", "reply": "", "valid": False}
    if "?" in t or low.startswith(("а ", "а\t", "что ", "как ", "когда ", "где ", "сколько ", "почему ")):
        return {"intent": "question", "value": "", "reply": "", "valid": False}
    return {"intent": "answer", "value": t, "reply": "", "valid": True}


def _coerce_intent(obj: dict, user_text: str) -> dict:
    """Нормализуем произвольный JSON от LLM в нашу структуру."""
    intent = str(obj.get("intent") or "").strip().lower()
    if intent not in VALID_INTENTS:
        intent = "answer" if obj.get("value") else "off_topic"
    value = str(obj.get("value") or "").strip()
    reply = str(obj.get("reply") or "").strip()
    valid = bool(obj.get("valid", bool(value) and intent == "answer"))
    if intent != "answer":
        valid = False
    # если LLM потерял value, но это answer — возьмём исходник
    if intent == "answer" and not value:
        value = user_text.strip()
    return {"intent": intent, "value": value, "reply": reply, "valid": valid}


def _parse_json_loose(text: str) -> Optional[dict]:
    if not text:
        return None
    # вытащим первый JSON-объект из текста
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def ai_classify_intent(
    shop,
    *,
    question: str,
    variable_name: str,
    user_text: str,
    catalog: str = "",
    shop_name: str = "",
) -> dict:
    """
    Классифицирует, что хочет клиент в ответ на вопрос `question` (ожидающий `variable_name`).

    Возвращает: {intent, value, reply, valid}.
    Никогда не бросает — в худшем случае отдаст эвристический ответ.
    """
    provider, key, model = _resolve_creds(shop)
    if not _has_creds(provider, key):
        return _heuristic_intent(user_text)

    system = (
        "Ты — классификатор сообщений клиентов цветочного магазина. "
        "Возвращай СТРОГО JSON, без пояснений, без markdown.\n\n"
        "Формат ответа: "
        '{"intent": "answer|question|switch_catalog|handoff|refuse|off_topic", '
        '"value": "извлечённое значение если intent=answer, иначе пустая строка", '
        '"reply": "короткий ответ клиенту (1–2 предложения) если intent != answer, иначе пустая строка", '
        '"valid": true/false}.\n\n'
        "Правила:\n"
        "- answer: клиент по существу ответил на вопрос.\n"
        "- question: клиент задал встречный вопрос (приоритет над answer, если вопрос явный).\n"
        "- switch_catalog: клиент хочет посмотреть (другие) варианты букетов/каталог/ассортимент.\n"
        "- handoff: клиент просит менеджера/оператора/человека.\n"
        "- refuse: клиент отказывается отвечать.\n"
        "- off_topic: сообщение не по теме вопроса.\n"
        "- valid=true только если value очевидно корректно для переменной.\n"
        "- Если intent != answer, сформулируй короткий дружелюбный reply, "
        "который отвечает на вопрос клиента и мягко возвращает к теме.\n"
    )
    shop_ctx = f"Магазин: «{shop_name}».\n" if shop_name else ""
    cat_ctx = (catalog + "\n") if catalog else ""
    prompt = (
        f"{shop_ctx}{cat_ctx}"
        f"Ожидаемая переменная: {variable_name}\n"
        f"Вопрос клиенту: {question}\n"
        f"Ответ клиента: {user_text}\n\n"
        "Верни только JSON."
    )

    try:
        if provider == "free":
            raw = _free_chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": prompt}],
                json_mode=True, temperature=0,
            )
        elif provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=key, timeout=settings.ai_timeout_seconds)
            r = client.messages.create(
                model=model, system=system, max_tokens=512, temperature=0,
                messages=[{"role": "user", "content": prompt + "\n\nReturn ONLY the JSON object."}],
            )
            parts = [b.text for b in (r.content or []) if getattr(b, "type", "") == "text"]
            raw = ("\n".join(parts)).strip()
        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=key, timeout=settings.ai_timeout_seconds)
            r = client.chat.completions.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = (r.choices[0].message.content or "").strip()
        else:
            import google.generativeai as genai
            genai.configure(api_key=key)
            m = genai.GenerativeModel(
                model_name=model,
                system_instruction=system,
                generation_config={"response_mime_type": "application/json", "temperature": 0},
            )
            r = m.generate_content(
                prompt,
                request_options={"timeout": settings.ai_timeout_seconds},
            )
            raw = (r.text or "").strip()
    except Exception as e:
        log.warning("ai_classify_intent call failed: %s", e)
        return _heuristic_intent(user_text)

    obj = _parse_json_loose(raw)
    if not obj:
        log.warning("ai_classify_intent: could not parse JSON: %r", raw[:200])
        return _heuristic_intent(user_text)
    return _coerce_intent(obj, user_text)
