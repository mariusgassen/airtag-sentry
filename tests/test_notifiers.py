from unittest.mock import MagicMock, patch

import pytest
from pywebpush import WebPushException

from airtag_sentry.db import PushSubscription
from airtag_sentry.notifiers.ntfy import NtfyNotifier
from airtag_sentry.notifiers.telegram import TelegramNotifier
from airtag_sentry.notifiers.webpush import WebPushConfig, WebPushNotifier


@patch("airtag_sentry.notifiers.ntfy.requests.post")
def test_ntfy_notifier_posts_to_topic(mock_post):
    mock_post.return_value.raise_for_status = MagicMock()
    NtfyNotifier("https://ntfy.sh/my-topic").send("Titel", "Nachricht")

    args, kwargs = mock_post.call_args
    assert args[0] == "https://ntfy.sh/my-topic"
    assert kwargs["data"] == b"Nachricht"
    assert kwargs["headers"]["Title"] == "Titel"


@patch("airtag_sentry.notifiers.telegram.requests.post")
def test_telegram_notifier_posts_message(mock_post):
    mock_post.return_value.raise_for_status = MagicMock()
    TelegramNotifier("bot-token", "12345").send("Titel", "Nachricht")

    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.telegram.org/botbot-token/sendMessage"
    assert kwargs["json"] == {"chat_id": "12345", "text": "Titel\nNachricht"}


@patch("airtag_sentry.notifiers.webpush.webpush")
@patch("airtag_sentry.notifiers.webpush.list_push_subscriptions")
@patch("airtag_sentry.notifiers.webpush.get_conn")
def test_webpush_notifier_sends_to_all_subscriptions(mock_get_conn, mock_list_subs, mock_webpush):
    mock_get_conn.return_value.__enter__.return_value = MagicMock()
    mock_list_subs.return_value = [
        PushSubscription(endpoint="https://push.example/a", p256dh="p1", auth="a1"),
        PushSubscription(endpoint="https://push.example/b", p256dh="p2", auth="a2"),
    ]
    cfg = WebPushConfig(public_key="pub", private_key="priv", subject="mailto:me@example.com")

    WebPushNotifier("postgresql://unused", cfg).send("Titel", "Nachricht")

    assert mock_webpush.call_count == 2
    endpoints = {call.kwargs["subscription_info"]["endpoint"] for call in mock_webpush.call_args_list}
    assert endpoints == {"https://push.example/a", "https://push.example/b"}


@patch("airtag_sentry.notifiers.webpush.remove_push_subscription")
@patch("airtag_sentry.notifiers.webpush.webpush")
@patch("airtag_sentry.notifiers.webpush.list_push_subscriptions")
@patch("airtag_sentry.notifiers.webpush.get_conn")
def test_webpush_notifier_prunes_expired_subscription(
    mock_get_conn, mock_list_subs, mock_webpush, mock_remove
):
    mock_get_conn.return_value.__enter__.return_value = MagicMock()
    mock_list_subs.return_value = [
        PushSubscription(endpoint="https://push.example/gone", p256dh="p1", auth="a1"),
    ]
    response = MagicMock(status_code=410)
    mock_webpush.side_effect = WebPushException("gone", response=response)
    cfg = WebPushConfig(public_key="pub", private_key="priv", subject="mailto:me@example.com")

    WebPushNotifier("postgresql://unused", cfg).send("Titel", "Nachricht")

    mock_remove.assert_called_once_with(mock_get_conn.return_value.__enter__.return_value, "https://push.example/gone")
