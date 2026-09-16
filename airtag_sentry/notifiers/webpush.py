from __future__ import annotations

import json
import logging

from pywebpush import WebPushException, webpush

from airtag_sentry.config import WebPushConfig
from airtag_sentry.db import get_conn, list_push_subscriptions, remove_push_subscription

logger = logging.getLogger(__name__)


class WebPushNotifier:
    def __init__(self, database_url: str, cfg: WebPushConfig) -> None:
        self._database_url = database_url
        self._cfg = cfg

    def send(self, title: str, message: str) -> None:
        payload = json.dumps({"title": title, "message": message})
        with get_conn(self._database_url) as conn:
            subscriptions = list_push_subscriptions(conn)
            if not subscriptions:
                # Otherwise a movement alert with zero push subscribers leaves
                # no trace at all - no success, no failure, nothing - which
                # is indistinguishable in the logs from web push never having
                # been attempted. This is the first thing to check if push
                # "seems enabled" in the dashboard but nothing ever arrives:
                # the toggle only reflects the browser's own subscription
                # state, not whether /api/push/subscribe's POST ever actually
                # reached and was persisted by the server.
                logger.info("No push subscriptions to notify.")
                return
            for sub in subscriptions:
                subscription_info = {
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                }
                try:
                    webpush(
                        subscription_info=subscription_info,
                        data=payload,
                        vapid_private_key=self._cfg.private_key,
                        vapid_claims={"sub": self._cfg.subject},
                    )
                    logger.info("Web push delivered to %s", sub.endpoint)
                except WebPushException as exc:
                    status = exc.response.status_code if exc.response is not None else None
                    if status in (404, 410):
                        logger.info("Pruning expired push subscription %s", sub.endpoint)
                        remove_push_subscription(conn, sub.endpoint)
                    else:
                        logger.exception("Web push delivery failed for %s", sub.endpoint)
