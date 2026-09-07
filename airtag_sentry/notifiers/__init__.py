"""Pluggable notification backends: ntfy.sh, Telegram, Web Push.

Each backend implements the same tiny Notifier protocol; build_notifiers() includes
whichever backends have their config/credentials present and broadcasts every alert
to all of them.
"""

from __future__ import annotations

import logging
from typing import Protocol

from airtag_sentry.config import Config

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    def send(self, title: str, message: str) -> None: ...


def build_notifiers(cfg: Config, conn) -> list[Notifier]:
    from airtag_sentry import keystore
    from airtag_sentry.db import get_telegram_credentials
    from airtag_sentry.notifiers.ntfy import NtfyNotifier
    from airtag_sentry.notifiers.telegram import TelegramNotifier
    from airtag_sentry.notifiers.webpush import WebPushNotifier

    notifiers: list[Notifier] = []
    if cfg.notifications.ntfy:
        notifiers.append(NtfyNotifier(cfg.notifications.ntfy.topic_url))
    telegram = get_telegram_credentials(conn)
    if telegram:
        bot_token = keystore.decrypt(cfg.key_encryption_key, telegram.bot_token_encrypted)
        notifiers.append(TelegramNotifier(bot_token, telegram.chat_id))
    if cfg.notifications.webpush:
        notifiers.append(WebPushNotifier(cfg.database_url, cfg.notifications.webpush))
    return notifiers


def notify_all(notifiers: list[Notifier], title: str, message: str) -> None:
    for notifier in notifiers:
        try:
            notifier.send(title, message)
        except Exception:
            logger.exception("Notifier %r failed to send", notifier)
