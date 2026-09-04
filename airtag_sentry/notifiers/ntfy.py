from __future__ import annotations

from urllib.parse import quote

import requests


class NtfyNotifier:
    def __init__(self, topic_url: str) -> None:
        self._topic_url = topic_url

    def send(self, title: str, message: str) -> None:
        # ntfy headers must be ASCII; percent-encode the title so umlauts etc. survive.
        requests.post(
            self._topic_url,
            data=message.encode("utf-8"),
            headers={"Title": quote(title), "Priority": "high"},
            timeout=10,
        ).raise_for_status()
