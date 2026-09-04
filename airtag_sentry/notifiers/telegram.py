from __future__ import annotations

import requests


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id

    def send(self, title: str, message: str) -> None:
        requests.post(
            self._url,
            json={"chat_id": self._chat_id, "text": f"{title}\n{message}"},
            timeout=10,
        ).raise_for_status()
