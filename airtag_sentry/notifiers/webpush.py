from __future__ import annotations

import base64
import json
import logging

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush

from airtag_sentry import keystore
from airtag_sentry.db import (
    WebPushKeys,
    get_conn,
    get_webpush_keys,
    list_push_subscriptions,
    remove_push_subscription,
    set_webpush_keys,
)

logger = logging.getLogger(__name__)

_VAPID_SUBJECT = "mailto:airtag-sentry@localhost"


def _generate_vapid_keys(key_encryption_key: str) -> WebPushKeys:
    """A fresh VAPID keypair, re-encoded as the url-safe base64 the Web Push
    spec (and pywebpush, and browsers' applicationServerKey) expect. Only
    called once, the first time a browser asks for the public key - see
    get_or_create_vapid_keys()."""
    vapid = Vapid02()
    vapid.generate_keys()
    public_raw = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    private_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    return WebPushKeys(
        public_key=base64.urlsafe_b64encode(public_raw).rstrip(b"=").decode(),
        private_key_encrypted=keystore.encrypt(
            key_encryption_key, base64.urlsafe_b64encode(private_raw).rstrip(b"=").decode()
        ),
        subject=_VAPID_SUBJECT,
    )


def get_or_create_vapid_keys(conn, key_encryption_key: str) -> WebPushKeys:
    """The dashboard's Settings panel has no "generate VAPID keys" step -
    this generates and persists the keypair transparently the first time a
    browser calls GET /api/push/vapid-public-key, so Web Push needs no setup
    at all beyond clicking the toggle (see CLAUDE.md's UI-first constraint)."""
    existing = get_webpush_keys(conn)
    if existing is not None:
        return existing
    set_webpush_keys(conn, _generate_vapid_keys(key_encryption_key))
    return get_webpush_keys(conn)  # re-read: a concurrent caller may have won the insert race


class WebPushNotifier:
    def __init__(self, database_url: str, key_encryption_key: str) -> None:
        self._database_url = database_url
        self._key_encryption_key = key_encryption_key

    def send(self, title: str, message: str) -> None:
        payload = json.dumps({"title": title, "message": message})
        with get_conn(self._database_url) as conn:
            keys = get_webpush_keys(conn)
            if keys is None:
                return  # no browser has ever asked for the public key, so nothing is subscribed
            private_key = keystore.decrypt(self._key_encryption_key, keys.private_key_encrypted)
            subscriptions = list_push_subscriptions(conn)
            for sub in subscriptions:
                subscription_info = {
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                }
                try:
                    webpush(
                        subscription_info=subscription_info,
                        data=payload,
                        vapid_private_key=private_key,
                        vapid_claims={"sub": keys.subject},
                    )
                except WebPushException as exc:
                    status = exc.response.status_code if exc.response is not None else None
                    if status in (404, 410):
                        logger.info("Pruning expired push subscription %s", sub.endpoint)
                        remove_push_subscription(conn, sub.endpoint)
                    else:
                        logger.exception("Web push delivery failed for %s", sub.endpoint)
