"""Мульти-тенантные Instagram-сессии (instagrapi), по одной на магазин."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

try:
    from instagrapi import Client
    from instagrapi.exceptions import ChallengeRequired, LoginRequired
except Exception:
    Client = None
    LoginRequired = Exception
    ChallengeRequired = Exception

SESSIONS_DIR = Path("ig_sessions")
SESSIONS_DIR.mkdir(exist_ok=True)


class IGSession:
    def __init__(self, shop_id: int):
        self.shop_id = shop_id
        self.cl: Client | None = None
        self.username = ""
        self.status = "disconnected"
        self._stop = threading.Event()
        self._thr: threading.Thread | None = None
        # _seen[thread_id] = last_message_id. Загружаем из Shop.ig_last_seen при старте.
        self._seen: dict[str, str] = {}
        # Флаг «первый poll после старта» — на нём не обрабатываем сообщения, только
        # фиксируем last_seen, чтобы не зафлудить клиентов историей.
        self._initial_sync_done = False
        self._load_seen()

    def _load_seen(self) -> None:
        try:
            from ..database import SessionLocal
            from ..models import Shop
            db = SessionLocal()
            try:
                s = db.get(Shop, self.shop_id)
                if s and isinstance(s.ig_last_seen, dict):
                    self._seen = dict(s.ig_last_seen)
                    self._initial_sync_done = True  # есть сохранённое состояние — обрабатываем сразу
            finally:
                db.close()
        except Exception:
            log.exception("IG: load _seen failed shop=%s", self.shop_id)

    def _persist_seen(self) -> None:
        try:
            from ..database import SessionLocal
            from ..models import Shop
            db = SessionLocal()
            try:
                s = db.get(Shop, self.shop_id)
                if s:
                    s.ig_last_seen = dict(self._seen)
                    db.commit()
            finally:
                db.close()
        except Exception:
            log.exception("IG: persist _seen failed shop=%s", self.shop_id)

    def _file(self) -> Path:
        return SESSIONS_DIR / f"shop_{self.shop_id}.json"

    def login(self, username: str, password: str, code: str = "", proxy: str = "") -> dict:
        if Client is None:
            return {"ok": False, "error": "instagrapi not installed"}
        cl = Client()

        # Эмулируем стабильное Android-устройство — Instagram реже флагает таких клиентов
        # как ботов (по сравнению с дефолтным fingerprint).
        try:
            cl.set_device({
                "app_version": "269.0.0.18.75",
                "android_version": 26,
                "android_release": "8.0.0",
                "dpi": "480dpi",
                "resolution": "1080x1920",
                "manufacturer": "Xiaomi",
                "device": "MI 8",
                "model": "MI 8",
                "cpu": "qcom",
                "version_code": "314665256",
            })
            cl.set_user_agent(
                "Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; Xiaomi; MI 8; MI 8; qcom; en_US; 314665256)"
            )
        except Exception:
            log.exception("IG: set_device failed")

        # Прокси (рекомендованно residential/mobile, чтобы обойти IP-блок IG)
        if proxy:
            try:
                cl.set_proxy(proxy)
            except Exception as e:
                return {"ok": False, "error": f"bad proxy: {e}"}

        try:
            f = self._file()
            if f.exists():
                try:
                    cl.load_settings(f)
                except Exception:
                    log.warning("IG: corrupt session file %s — removing", f)
                    try:
                        f.unlink()
                    except Exception:
                        pass
            cl.login(username, password, verification_code=code or None)
            cl.dump_settings(f)
            self.cl = cl
            self.username = username
            self.status = "connected"
            self._start_poll()
            return {"ok": True, "status": "connected"}
        except ChallengeRequired as e:
            return {"ok": False, "error": "challenge_required", "detail": str(e)}
        except Exception as e:
            msg = str(e) or e.__class__.__name__
            low = msg.lower()
            hint = None
            # Когда Instagram блокирует/перенаправляет, instagrapi падает на JSON.parse
            # с сообщением "Expecting value: line 1 column 1 (char 0)" — это HTML-ответ
            # вместо JSON, фактически тот же признак IP-блока/challenge.
            if "expecting value" in low or "json" in low and "decode" in low:
                hint = "ip_blocked"
                msg = (
                    "Instagram вернул HTML вместо JSON (обычно при блокировке IP "
                    "или редиректе на checkpoint). Подключите residential/mobile прокси."
                )
            elif ("ip" in low and ("block" in low or "blacklist" in low or "suspicious" in low)) \
                    or "few minutes" in low or "back to" in low or "try again later" in low:
                hint = "ip_blocked"
            elif "password" in low and "incorrect" in low:
                hint = "bad_password"
            elif "checkpoint" in low or "challenge" in low or "two_factor" in low or "two-factor" in low:
                hint = "challenge_required"
            elif "proxy" in low:
                hint = "bad_proxy"
            return {"ok": False, "error": msg, "hint": hint}

    def logout(self):
        self._stop.set()
        if self.cl:
            try:
                self.cl.logout()
            except Exception:
                pass
        self.cl = None
        self.status = "disconnected"
        f = self._file()
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass

    def info(self) -> dict:
        return {"status": self.status, "username": self.username, "connected": self.cl is not None}

    def send(self, user_id: str, text: str) -> dict:
        if not self.cl:
            return {"ok": False, "error": "not connected"}
        try:
            self.cl.direct_send(text, user_ids=[int(user_id)])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _start_poll(self, interval: int = 8):
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()

        def loop():
            while not self._stop.is_set():
                try:
                    self._poll_once()
                except Exception:
                    log.exception("IG shop %s poll failed", self.shop_id)
                self._stop.wait(interval)

        self._thr = threading.Thread(target=loop, daemon=True)
        self._thr.start()

    def _poll_once(self):
        if not self.cl:
            return
        try:
            threads = self.cl.direct_threads(amount=10)
        except LoginRequired:
            self.status = "login_required"
            return
        changed = False
        first_run = not self._initial_sync_done
        for th in threads:
            tid = str(th.id)
            items = th.messages or []
            if first_run:
                # На первом запуске после старта/login без сохранённого _seen — только
                # фиксируем «всё, что есть, считается прочитанным», чтобы не флудить
                # клиентов историей сообщений.
                if items:
                    self._seen[tid] = str(items[0].id)
                    changed = True
                continue

            last_seen = self._seen.get(tid)
            new_items = []
            for it in items:
                if str(it.id) == last_seen:
                    break
                if it.user_id == self.cl.user_id:
                    continue
                if it.item_type != "text":
                    continue
                new_items.append(it)
            new_items.reverse()
            for it in new_items:
                try:
                    from ..dispatcher import handle_incoming, persist_incoming
                    user = next((u for u in th.users if u.pk == it.user_id), None)
                    name = user.username if user else str(it.user_id)
                    inbox_id = persist_incoming(self.shop_id, "instagram", str(it.user_id), it.text or "", name)
                    handle_incoming(self.shop_id, "instagram", str(it.user_id), it.text or "", name, inbox_id=inbox_id)
                except Exception:
                    log.exception("IG shop %s dispatch failed", self.shop_id)
            if items:
                new_last = str(items[0].id)
                if self._seen.get(tid) != new_last:
                    self._seen[tid] = new_last
                    changed = True
        if first_run:
            self._initial_sync_done = True
        if changed:
            self._persist_seen()


class IGManager:
    def __init__(self):
        self._sessions: dict[int, IGSession] = {}
        self._lock = threading.Lock()

    def get(self, shop_id: int) -> IGSession:
        with self._lock:
            s = self._sessions.get(shop_id)
            if not s:
                s = IGSession(shop_id)
                self._sessions[shop_id] = s
            return s


ig_manager = IGManager()
