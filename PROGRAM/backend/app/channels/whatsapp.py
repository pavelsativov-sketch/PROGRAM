"""WhatsApp client (sync httpx) — общается с Node-мостом. Магазин = shop_id."""
from __future__ import annotations

import httpx

from ..config import settings


class WhatsAppBridge:
    def __init__(self):
        self.headers = {"X-Bridge-Secret": settings.wa_bridge_secret}

    @property
    def base(self) -> str:
        return settings.wa_bridge_url.rstrip("/")

    def _get(self, path: str) -> dict:
        try:
            with httpx.Client(timeout=10) as c:
                r = c.get(f"{self.base}{path}", headers=self.headers)
                return r.json()
        except Exception as e:
            return {"status": "down", "error": str(e)}

    def _post(self, path: str, json=None) -> dict:
        try:
            with httpx.Client(timeout=15) as c:
                r = c.post(f"{self.base}{path}", headers=self.headers, json=json)
                if r.status_code >= 400:
                    return {"ok": False, "error": r.text}
                return r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def status(self, shop_id: int) -> dict:
        return self._get(f"/shops/{shop_id}/status")

    def qr(self, shop_id: int) -> dict:
        return self._get(f"/shops/{shop_id}/qr")

    def connect(self, shop_id: int) -> dict:
        return self._post(f"/shops/{shop_id}/connect")

    def send(self, shop_id: int, to: str, text: str) -> dict:
        return self._post(f"/shops/{shop_id}/send", json={"to": to, "text": text})

    def logout(self, shop_id: int) -> dict:
        return self._post(f"/shops/{shop_id}/logout")


whatsapp = WhatsAppBridge()
