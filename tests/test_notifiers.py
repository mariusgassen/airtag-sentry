import json
from unittest.mock import MagicMock, patch

import pytest
from pywebpush import WebPushException

from airtag_sentry.db import MqttCredentials, PushSubscription
from airtag_sentry.notifiers.homeassistant import HomeAssistantPublisher, MqttConfig, build_ha_publisher
from airtag_sentry.notifiers.telegram import TelegramNotifier
from airtag_sentry.notifiers.webpush import WebPushConfig, WebPushNotifier


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


def _fake_publisher():
    with patch("airtag_sentry.notifiers.homeassistant.mqtt.Client") as mock_client_cls:
        publisher = HomeAssistantPublisher(
            MqttConfig(host="broker", port=1883, username=None, password=None, use_tls=False)
        )
    return publisher, mock_client_cls.return_value


def test_publish_airtag_publishes_gps_tracker_and_text_battery_sensor():
    """AirTags only ever report a qualitative battery bucket (see
    tracker._battery_level), so the battery sensor must be a plain text
    sensor, not a numeric device_class:battery one (that's owner devices,
    see test_publish_owner_device below)."""
    publisher, mock_client = _fake_publisher()

    publisher.publish_airtag("my-bike", "My Bike", 52.5, 13.4, 5.0, "low")

    topics = {call.args[0]: call.args[1] for call in mock_client.publish.call_args_list}
    tracker_config = json.loads(topics["homeassistant/device_tracker/airtag_sentry_airtag_my-bike_tracker/config"])
    assert tracker_config["source_type"] == "gps"
    assert tracker_config["state_topic"] == "airtag_sentry/airtag_sentry_airtag_my-bike/state"
    attributes = json.loads(topics["airtag_sentry/airtag_sentry_airtag_my-bike/attributes"])
    assert attributes == {"latitude": 52.5, "longitude": 13.4, "gps_accuracy": 5.0}

    battery_config = json.loads(topics["homeassistant/sensor/airtag_sentry_airtag_my-bike_battery/config"])
    assert "device_class" not in battery_config
    assert topics["airtag_sentry/airtag_sentry_airtag_my-bike/battery"] == "low"


def test_publish_owner_device_publishes_numeric_battery_percent_sensor():
    publisher, mock_client = _fake_publisher()

    publisher.publish_owner_device("dev-1", "iPhone", 52.5, 13.4, 5.0, 0.73)

    topics = {call.args[0]: call.args[1] for call in mock_client.publish.call_args_list}
    battery_config = json.loads(topics["homeassistant/sensor/airtag_sentry_device_dev-1_battery/config"])
    assert battery_config["device_class"] == "battery"
    assert battery_config["unit_of_measurement"] == "%"
    assert topics["airtag_sentry/airtag_sentry_device_dev-1/battery"] == "73"


@patch("airtag_sentry.notifiers.homeassistant.get_mqtt_credentials")
def test_build_ha_publisher_returns_none_when_not_configured(mock_get_creds):
    mock_get_creds.return_value = None
    assert build_ha_publisher(MagicMock(), MagicMock()) is None


@patch("airtag_sentry.notifiers.homeassistant.HomeAssistantPublisher")
@patch("airtag_sentry.notifiers.homeassistant.get_mqtt_credentials")
def test_build_ha_publisher_decrypts_password(mock_get_creds, mock_publisher_cls):
    mock_get_creds.return_value = MqttCredentials(
        host="broker", port=8883, username="user", password_encrypted="encrypted", use_tls=True
    )
    cfg = MagicMock()
    cfg.key_encryption_key = "key"
    with patch("airtag_sentry.notifiers.homeassistant.keystore.decrypt", return_value="secret") as mock_decrypt:
        build_ha_publisher(cfg, MagicMock())

    mock_decrypt.assert_called_once_with("key", "encrypted")
    config = mock_publisher_cls.call_args.args[0]
    assert config == MqttConfig(host="broker", port=8883, username="user", password="secret", use_tls=True)
