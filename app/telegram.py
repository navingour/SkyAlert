import requests
from app.logger import logger


class TelegramNotifier:

    def __init__(self, token, chat_id, photo_enabled=True):
        self.token = str(token).strip() if token else ""
        self.chat_id = str(chat_id).strip() if chat_id else ""
        self.photo_enabled = photo_enabled

    def verify_token(self):
        """Validates bot token against Telegram getMe API."""
        if not self.token:
            return {"ok": False, "error": "Bot token is empty"}
        try:
            url = f"https://api.telegram.org/bot{self.token}/getMe"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data.get("ok"):
                return {"ok": True, "bot": data.get("result", {})}
            else:
                return {"ok": False, "error": data.get("description", "Invalid bot token")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def send(self, message, photo_url=None, silent=False):
        """Sends an HTML formatted message or photo card to configured Telegram chat/channel."""
        if not self.token or not self.chat_id:
            logger.warning("Telegram token or chat_id not configured")
            return None

        # Try sending photo with caption if photo_url is provided and photo_enabled
        if photo_url and self.photo_enabled:
            try:
                photo_url_api = f"https://api.telegram.org/bot{self.token}/sendPhoto"
                payload = {
                    "chat_id": self.chat_id,
                    "photo": photo_url,
                    "caption": message[:1024],
                    "parse_mode": "HTML",
                    "disable_notification": silent
                }
                res = requests.post(photo_url_api, json=payload, timeout=15)
                if res.status_code == 200:
                    return res.json()
                logger.warning(f"Telegram sendPhoto failed ({res.status_code}): {res.text}. Falling back to sendMessage.")
            except Exception as e:
                logger.warning(f"Telegram sendPhoto error: {e}. Falling back to sendMessage.")

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "disable_notification": silent
        }

        response = requests.post(
            url,
            json=payload,
            timeout=15
        )

        response.raise_for_status()
        return response.json()
