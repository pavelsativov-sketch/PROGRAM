"""Flow Engine — мультитенантное исполнение графа."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from . import models
from .agent import run_agent_turn
from .ai import ai_classify_intent, ai_extract, ai_reply
from .invoice import create_invoice_for_conversation
from .variables import validate_variable

log = logging.getLogger(__name__)


def _trigger_handoff(db: Session, shop: models.Shop, conv: models.Conversation, reason: str = "") -> None:
    """Ставит диалог в handoff и шлёт уведомление во все каналы (best-effort)."""
    conv.status = "handoff"
    try:
        from . import notifications
        notifications.notify_handoff(db, shop, conv, reason=reason)
    except Exception:
        log.exception("notify_handoff failed conv=%s", conv.id)


def _history(conv: models.Conversation) -> list[dict]:
    out = []
    for m in conv.messages:
        if m.role == "user":
            out.append({"role": "user", "content": m.text})
        elif m.role == "bot":
            out.append({"role": "assistant", "content": m.text})
    return out


def _node_by_id(graph, nid):
    for n in graph.get("nodes", []):
        if n.get("id") == nid:
            return n
    return None


def _next_node_id(graph, from_id, handle=None):
    """
    Правила:
    - Если указан handle — сначала ищем edge ровно с этим sourceHandle.
    - Иначе ищем edge без sourceHandle (или с пустым).
    - Никогда не «сматчим» true-ветку, когда просили false, и наоборот.
    """
    edges = [e for e in graph.get("edges", []) if e.get("source") == from_id]
    if handle is not None:
        for e in edges:
            if e.get("sourceHandle") == handle:
                return e.get("target")
        # явный fallback на дефолтную ветку без handle
        for e in edges:
            if not e.get("sourceHandle"):
                return e.get("target")
        return None
    # handle не задан — идём по первой «дефолтной» ветке
    for e in edges:
        if not e.get("sourceHandle"):
            return e.get("target")
    return edges[0].get("target") if edges else None


def _find_start(graph):
    for n in graph.get("nodes", []):
        kind = (n.get("data") or {}).get("kind") or n.get("type")
        if kind == "start":
            return n.get("id")
    targets = {e.get("target") for e in graph.get("edges", [])}
    for n in graph.get("nodes", []):
        if n.get("id") not in targets:
            return n.get("id")
    nodes = graph.get("nodes") or []
    return nodes[0]["id"] if nodes else None


def _kind(node):
    return (node.get("data") or {}).get("kind") or node.get("type") or "message"


def _render(text, variables):
    try:
        return text.format(**variables) if text else ""
    except Exception:
        return text or ""


def _send(db, conv, text, meta=None):
    if not text:
        return
    meta = dict(meta or {})
    meta.setdefault("sent", False)
    db.add(models.Message(conversation_id=conv.id, role="bot", text=text, meta=meta))
    db.flush()


def _catalog_items(db, shop_id):
    return db.query(models.Product).filter_by(shop_id=shop_id, is_active=True).all()


def _catalog_text(db, shop_id):
    items = _catalog_items(db, shop_id)
    if not items:
        return "Каталог пуст."
    lines = ["🌸 Наш каталог:"]
    for idx, p in enumerate(items, start=1):
        category = p.category or "Каталог"
        availability = "есть сегодня" if getattr(p, "available_today", True) else "под заказ"
        image = f"\n  Фото: {p.image_url}" if p.image_url else ""
        lines.append(f"{idx}. [{category}] {p.name} — {p.price:.0f} ₽, {availability}\n  {p.description}{image}")
    lines.append("\nКакой букет вам нравится?")
    return "\n".join(lines)


def _catalog_for_ai(db, shop) -> str:
    """Короткий JSON-подобный каталог для подмешивания в system prompt AI-узла."""
    items = _catalog_items(db, shop.id)
    if not items:
        return ""
    lines = [f"Каталог магазина «{shop.name}» (цены в {shop.currency}):"]
    for p in items[:40]:
        category = p.category or "Каталог"
        availability = "есть сегодня" if getattr(p, "available_today", True) else "под заказ"
        image = f", photo={p.image_url}" if p.image_url else ""
        lines.append(f"- [{category}] {p.name}: {p.price:.0f}, {availability}, {p.description}{image}")
    lines.append("Не придумывай букеты и цены вне этого списка.")
    return "\n".join(lines)


def _execute_node(db, shop, conv, node, user_input):
    kind = _kind(node)
    data = node.get("data") or {}
    vars_ = dict(conv.variables or {})

    if kind == "start":
        return False, _next_node_id(conv.flow.graph, node["id"])

    if kind == "message":
        _send(db, conv, _render(data.get("text", ""), vars_))
        return False, _next_node_id(conv.flow.graph, node["id"])

    if kind == "agent":
        # Полноценный LLM-агент с tools. Стоит на узле и ведёт диалог
        # до handoff, инвойса или закрытия.
        run_agent_turn(
            db, shop, conv, user_input,
            required_slots=data.get("required_slots"),
            node_data=data,
        )
        # Агент сам переключает conv.status. Если диалог завершился — идём дальше по графу.
        if conv.status in {"pending_payment", "payment_review", "handoff", "closed"}:
            return False, _next_node_id(conv.flow.graph, node["id"])
        # иначе — ждём следующий ответ пользователя на том же узле
        return True, node["id"]

    if kind == "ai":
        base_system = data.get("system_prompt") or (
            f"Ты — вежливый ассистент магазина «{shop.name}». Отвечай коротко, тёпло, помогай выбрать букет и оформить заказ."
        )
        catalog = _catalog_for_ai(db, shop)
        system = f"{base_system}\n\n{catalog}" if catalog else base_system
        if user_input is None:
            reply = ai_reply(shop, system, _history(conv), "Начни диалог приветствием.")
        else:
            reply = ai_reply(shop, system, _history(conv), user_input)
        _send(db, conv, reply)
        if data.get("wait_user", True) and user_input is None:
            return True, node["id"]
        return False, _next_node_id(conv.flow.graph, node["id"])

    if kind == "collect":
        variable = data.get("variable") or "value"
        question = _render(data.get("question", "Уточните?"), vars_)
        if user_input is None:
            _send(db, conv, question)
            return True, node["id"]

        # 1) Классифицируем намерение клиента (LLM или эвристика).
        catalog_ctx = _catalog_for_ai(db, shop)
        decision = ai_classify_intent(
            shop,
            question=question,
            variable_name=variable,
            user_text=user_input,
            catalog=catalog_ctx,
            shop_name=shop.name,
        )
        intent = decision.get("intent", "answer")

        # 2) Оператор. НЕ переключаем сразу — спрашиваем подтверждение.
        # Реальное переключение делает _global_command в run_conversation, когда
        # клиент явно подтвердит ("да"/"подключите менеджера"). Иначе диалог продолжается.
        if intent == "handoff":
            if vars_.get("_handoff_pending"):
                # клиент уже спрашивал менеджера — но не подтвердил «да» (иначе бы сработал _global_command).
                # Не зацикливаемся: ещё раз спрашиваем кратко и продолжаем.
                _send(db, conv, "Хорошо, как только напишете «да» — переключу на менеджера. А пока могу помочь сам.")
            else:
                vars_["_handoff_pending"] = True
                conv.variables = vars_
                _send(db, conv, decision.get("reply") or "Хотите, подключу менеджера? Напишите «да», и я переключу. А пока могу помочь сам.")
            _send(db, conv, question)
            return True, node["id"]

        # 3) Клиент просит каталог/другие варианты
        if intent == "switch_catalog":
            if decision.get("reply"):
                _send(db, conv, decision["reply"])
            _send(db, conv, _catalog_text(db, shop.id))
            _send(db, conv, question)  # вернули к вопросу
            return True, node["id"]

        # 4) Клиент задал встречный вопрос
        if intent == "question":
            reply = decision.get("reply")
            if not reply:
                system = (
                    f"Ты — ассистент магазина «{shop.name}». Коротко ответь на вопрос клиента, "
                    f"используя каталог ниже.\n\n{catalog_ctx}"
                )
                reply = ai_reply(shop, system, _history(conv), user_input)
            _send(db, conv, reply)
            _send(db, conv, question)  # мягко возвращаем к нашей теме
            return True, node["id"]

        # 5) Отказ — логируем, переходим дальше с пустым значением (по умолчанию дефолт у бизнеса)
        if intent == "refuse":
            _send(db, conv, decision.get("reply") or "Хорошо, пропустим этот шаг.")
            vars_[variable] = ""
            conv.variables = vars_
            db.flush()
            return False, _next_node_id(conv.flow.graph, node["id"])

        # 6) Не по теме — мягко возвращаем
        if intent == "off_topic":
            _send(db, conv, decision.get("reply") or "Давайте вернёмся к заказу.")
            _send(db, conv, question)
            return True, node["id"]

        # 7) answer — извлекаем и валидируем
        raw_value = decision.get("value") or user_input
        ep = data.get("extract_prompt")
        if ep and (not decision.get("valid") or raw_value == user_input):
            raw_value = ai_extract(shop, ep, user_input) or raw_value

        ok, norm, hint = validate_variable(variable, raw_value)
        if not ok:
            _send(db, conv, hint or "Уточните, пожалуйста.")
            _send(db, conv, question)
            return True, node["id"]

        vars_[variable] = norm
        conv.variables = vars_
        db.flush()
        return False, _next_node_id(conv.flow.graph, node["id"])

    if kind == "catalog":
        if user_input is None:
            _send(db, conv, _catalog_text(db, shop.id))
            return True, node["id"]

        # Тот же интент-классификатор: вопрос / другой каталог / оператор / выбор
        decision = ai_classify_intent(
            shop,
            question="Выберите букет из каталога",
            variable_name="chosen_product",
            user_text=user_input,
            catalog=_catalog_for_ai(db, shop),
            shop_name=shop.name,
        )
        intent = decision.get("intent", "answer")

        if intent == "handoff":
            if vars_.get("_handoff_pending"):
                _send(db, conv, "Если хотите менеджера — напишите «да», переключу. Иначе помогу сам.")
            else:
                vars_["_handoff_pending"] = True
                conv.variables = vars_
                _send(db, conv, decision.get("reply") or "Хотите, подключу менеджера? Напишите «да», и я переключу. А пока могу помочь сам.")
            return True, node["id"]

        if intent in {"question", "off_topic"}:
            reply = decision.get("reply")
            if not reply:
                system = (
                    f"Ты — ассистент магазина «{shop.name}». Ответь коротко, опираясь на каталог.\n\n"
                    f"{_catalog_for_ai(db, shop)}"
                )
                reply = ai_reply(shop, system, _history(conv), user_input)
            _send(db, conv, reply)
            return True, node["id"]

        if intent == "switch_catalog":
            _send(db, conv, _catalog_text(db, shop.id))  # текст уже заканчивается "Какой букет вам нравится?"
            return True, node["id"]

        # answer — выбранный продукт
        vars_["chosen_product"] = decision.get("value") or user_input
        conv.variables = vars_
        db.flush()
        return False, _next_node_id(conv.flow.graph, node["id"])

    if kind == "condition":
        variable = data.get("variable")
        keywords = data.get("keywords") or []
        value = str(vars_.get(variable, "") or user_input or "").lower()
        matched = any(k.lower() in value for k in keywords) if keywords else bool(value)
        return False, _next_node_id(conv.flow.graph, node["id"], handle="true" if matched else "false")

    if kind == "order_summary":
        lines = ["Проверьте заказ:"]
        for k, v in vars_.items():
            lines.append(f"• {k}: {v}")
        _send(db, conv, "\n".join(lines))
        return False, _next_node_id(conv.flow.graph, node["id"])

    if kind == "invoice":
        order = create_invoice_for_conversation(db, shop, conv, data)
        text = (
            f"Счёт №{order.id} на сумму {order.total:.0f} {shop.currency}\n"
            f"Kaspi оплата/QR: {order.payment_link}\n"
            f"После перевода нажмите «Я оплатил через Kaspi», менеджер проверит платеж и подтвердит доставку."
        )
        _send(db, conv, text, meta={"order_id": order.id, "payment_link": order.payment_link})
        conv.status = "pending_payment"
        return False, _next_node_id(conv.flow.graph, node["id"])

    if kind == "handoff":
        _send(db, conv, data.get("text") or "Передаю диалог менеджеру.")
        _trigger_handoff(db, shop, conv, reason="сценарий: узел handoff")
        return True, node["id"]

    if kind == "end":
        _send(db, conv, data.get("text") or "Спасибо! Хорошего дня 🌷")
        conv.status = "closed"
        return True, None

    log.warning("Unknown node kind: %s", kind)
    return False, _next_node_id(conv.flow.graph, node["id"])


GLOBAL_CMDS = {
    # Триггерим handoff только на явные просьбы «дайте/позовите/хочу/нужен … оператора/менеджера/живого человека».
    # Иначе слова «менеджер»/«оператор» (например в контексте «я менеджер магазина») валили диалог в handoff.
    "handoff": (
        "позови оператор", "позовите оператор", "дайте оператор", "хочу оператор", "нужен оператор",
        "позови менеджер", "позовите менеджер", "дайте менеджер", "хочу менеджер", "нужен менеджер",
        "соедините с оператор", "соедините с менеджер",
        "живой человек", "позовите человека", "хочу человека", "переключи на человек",
    ),
    "restart": ("начать сначала", "начнём сначала", "отмена заказа", "/reset", "рестарт", "начать заново"),
    "stop": ("стоп ", "стоп!", "хватит ", "прекрати", "unsubscribe", "отписаться"),
}


def _global_command(text: str) -> Optional[str]:
    low = (text or "").strip().lower()
    if not low:
        return None
    for cmd, words in GLOBAL_CMDS.items():
        if any(w in low for w in words):
            return cmd
    return None


def run_conversation(db: Session, shop: models.Shop, conv: models.Conversation, user_input: str | None):
    # Если диалог отдан менеджеру — AI не вмешивается, только сохраняем сообщение клиента.
    if conv.status == "handoff":
        if user_input is not None:
            db.add(models.Message(conversation_id=conv.id, role="user", text=user_input))
            db.flush()
        return
    # Бот выключен в настройках — не вмешиваемся AI, передаём менеджеру и алертим.
    if not getattr(shop, "bot_enabled", True):
        if user_input is not None:
            db.add(models.Message(conversation_id=conv.id, role="user", text=user_input))
            db.flush()
        _trigger_handoff(db, shop, conv, reason="бот выключен в настройках")
        try:
            from . import notifications
            notifications.notify_bot_disabled(db, shop)
        except Exception:
            log.exception("notify_bot_disabled failed shop=%s", shop.id)
        db.flush()
        return
    if not conv.flow or not conv.flow.graph or not conv.flow.graph.get("nodes"):
        _send(db, conv, "Сценарий не настроен.")
        return
    graph = conv.flow.graph
    if user_input is not None:
        db.add(models.Message(conversation_id=conv.id, role="user", text=user_input))
        db.flush()

        # Если ранее бот предложил подключить менеджера — короткое «да/ок/давайте» подтверждает.
        vars_now = dict(conv.variables or {})
        if vars_now.get("_handoff_pending"):
            low = (user_input or "").strip().lower()
            yes_words = ("да", "ага", "угу", "ок", "окей", "хорошо", "давай", "давайте", "подключи", "подключите", "yes", "y")
            if any(low == w or low.startswith(w + " ") or low.startswith(w + ",") or low.startswith(w + ".") or low.startswith(w + "!") for w in yes_words):
                _send(db, conv, "Хорошо, передаю диалог менеджеру 🌷")
                _trigger_handoff(db, shop, conv, reason="клиент подтвердил подключение менеджера")
                vars_now.pop("_handoff_pending", None)
                conv.variables = vars_now
                db.flush()
                return
            # Любой не-«да» снимает флаг и возвращает к обычному диалогу.
            vars_now.pop("_handoff_pending", None)
            conv.variables = vars_now
            db.flush()

        cmd = _global_command(user_input)
        if cmd == "handoff":
            _send(db, conv, "Передаю диалог менеджеру, он скоро ответит 🌷")
            _trigger_handoff(db, shop, conv, reason="клиент попросил менеджера")
            db.flush()
            return
        if cmd == "stop":
            _send(db, conv, "Хорошо, остановились. Напишите, когда будет удобно вернуться.")
            conv.status = "closed"
            db.flush()
            return
        if cmd == "restart":
            conv.current_node_id = ""
            conv.variables = {}
            conv.status = "active"
            _send(db, conv, "Окей, начинаем заново.")
            user_input = None

    current_id = conv.current_node_id or _find_start(graph)
    if not current_id:
        return
    safety = 0
    pending = user_input
    SAFETY_LIMIT = 50
    while current_id and safety < SAFETY_LIMIT:
        safety += 1
        node = _node_by_id(graph, current_id)
        if not node:
            break
        waiting, nxt = _execute_node(db, shop, conv, node, pending)
        pending = None
        if waiting:
            conv.current_node_id = current_id
            db.flush()
            return
        current_id = nxt
    if safety >= SAFETY_LIMIT:
        log.error(
            "flow safety guard hit shop=%s conv=%s last_node=%s — возможный цикл в графе",
            shop.id, conv.id, current_id,
        )
        _send(db, conv, "Ой, что-то пошло не так. Передаю диалог менеджеру.")
        _trigger_handoff(db, shop, conv, reason="сбой сценария (safety guard)")
    conv.current_node_id = current_id or ""
    db.flush()


# ---------- Валидация графа (используется роутером flows) ----------
VALID_KINDS = {
    "start", "message", "agent", "ai", "collect", "catalog",
    "condition", "order_summary", "invoice", "handoff", "end",
}


def validate_graph(graph: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ["graph must be an object"]
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ["nodes/edges must be arrays"]
    if not nodes:
        return ["graph has no nodes"]

    ids = set()
    kinds_count: dict[str, int] = {}
    for n in nodes:
        if not isinstance(n, dict) or "id" not in n:
            errors.append("node without id")
            continue
        if n["id"] in ids:
            errors.append(f"duplicate node id: {n['id']}")
        ids.add(n["id"])
        k = (n.get("data") or {}).get("kind") or n.get("type")
        if k and k not in VALID_KINDS:
            errors.append(f"unknown kind '{k}' on node {n['id']}")
        kinds_count[k] = kinds_count.get(k, 0) + 1

    if kinds_count.get("start", 0) > 1:
        errors.append("more than one start node")

    for e in edges:
        if not isinstance(e, dict):
            errors.append("edge must be an object"); continue
        s, t = e.get("source"), e.get("target")
        if s not in ids:
            errors.append(f"edge source '{s}' is not a known node")
        if t not in ids:
            errors.append(f"edge target '{t}' is not a known node")

    # Достижимость из start (если есть)
    start = _find_start(graph)
    if start and start in ids:
        seen = {start}
        stack = [start]
        adj: dict[str, list[str]] = {}
        for e in edges:
            adj.setdefault(e.get("source"), []).append(e.get("target"))
        while stack:
            v = stack.pop()
            for u in adj.get(v, []):
                if u not in seen:
                    seen.add(u); stack.append(u)
        unreachable = ids - seen
        if unreachable:
            errors.append(f"unreachable nodes: {sorted(unreachable)}")

    return errors
