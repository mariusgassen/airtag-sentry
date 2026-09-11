"""Home Assistant MQTT Discovery publisher.

Publishes retained MQTT messages so Home Assistant auto-creates a
device_tracker (position) + battery sensor entity per AirTag/owner device,
per the MQTT Discovery protocol
(https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery). No custom
HA integration/HACS component to maintain - HA does the entity creation
itself from whatever config topics show up.

One short-lived connection per poll cycle (built in build_ha_publisher,
closed by the caller once the poll is done), matching this codebase's
"one connection per call" style (see db.py's module docstring) rather than a
persistent background client to manage across restarts.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re

import paho.mqtt.client as mqtt

from airtag_sentry import keystore
from airtag_sentry.config import Config
from airtag_sentry.db import MqttCredentials, get_mqtt_credentials

logger = logging.getLogger(__name__)

_DISCOVERY_PREFIX = "homeassistant"
_STATE_PREFIX = "airtag_sentry"
_UNSAFE_ID_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


@dataclasses.dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    use_tls: bool


class HomeAssistantPublisher:
    def __init__(self, config: MqttConfig) -> None:
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if config.username:
            self._client.username_pw_set(config.username, config.password)
        if config.use_tls:
            self._client.tls_set()
        self._client.connect(config.host, config.port, keepalive=10)
        self._client.loop_start()

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def publish_airtag(
        self,
        airtag_id: str,
        name: str,
        lat: float,
        lon: float,
        accuracy: float | None,
        battery_level: str | None,
    ) -> None:
        unique_id = f"airtag_sentry_airtag_{_UNSAFE_ID_CHARS.sub('_', airtag_id)}"
        self._publish_tracker(unique_id, name, lat, lon, accuracy)
        if battery_level is not None:
            # AirTags only ever report a qualitative FindMy.py battery bucket
            # (full/medium/low/very_low - see tracker._battery_level), not a
            # percentage, so this is a plain text sensor rather than the
            # numeric device_class:battery one owner devices get below.
            self._publish_text_sensor(unique_id, "Battery", battery_level)

    def publish_owner_device(
        self,
        device_id: str,
        name: str,
        lat: float,
        lon: float,
        accuracy: float | None,
        battery_fraction: float | None,
    ) -> None:
        unique_id = f"airtag_sentry_device_{_UNSAFE_ID_CHARS.sub('_', device_id)}"
        self._publish_tracker(unique_id, name, lat, lon, accuracy)
        if battery_fraction is not None:
            self._publish_battery_sensor(unique_id, round(battery_fraction * 100))

    def _publish_tracker(self, unique_id: str, name: str, lat: float, lon: float, accuracy: float | None) -> None:
        device = {"identifiers": [unique_id], "name": name, "manufacturer": "AirTag Sentry"}
        tracker_id = f"{unique_id}_tracker"
        state_topic = f"{_STATE_PREFIX}/{unique_id}/state"
        attributes_topic = f"{_STATE_PREFIX}/{unique_id}/attributes"

        self._publish_json(
            f"{_DISCOVERY_PREFIX}/device_tracker/{tracker_id}/config",
            {
                "name": None,
                "unique_id": tracker_id,
                "source_type": "gps",
                "state_topic": state_topic,
                "json_attributes_topic": attributes_topic,
                "device": device,
            },
        )
        # source_type "gps" makes Home Assistant derive home/not_home (or a
        # zone name) from the lat/lon attributes itself - this literal state
        # value is required by the schema but otherwise ignored by HA.
        self._client.publish(state_topic, "not_home", retain=True, qos=1)
        self._publish_json(attributes_topic, {"latitude": lat, "longitude": lon, "gps_accuracy": accuracy})

    def _publish_battery_sensor(self, unique_id: str, battery_percent: int) -> None:
        device = {"identifiers": [unique_id]}
        sensor_id = f"{unique_id}_battery"
        state_topic = f"{_STATE_PREFIX}/{unique_id}/battery"
        self._publish_json(
            f"{_DISCOVERY_PREFIX}/sensor/{sensor_id}/config",
            {
                "name": "Battery",
                "unique_id": sensor_id,
                "device_class": "battery",
                "unit_of_measurement": "%",
                "state_topic": state_topic,
                "device": device,
            },
        )
        self._client.publish(state_topic, str(battery_percent), retain=True, qos=1)

    def _publish_text_sensor(self, unique_id: str, label: str, value: str) -> None:
        device = {"identifiers": [unique_id]}
        sensor_id = f"{unique_id}_battery"
        state_topic = f"{_STATE_PREFIX}/{unique_id}/battery"
        self._publish_json(
            f"{_DISCOVERY_PREFIX}/sensor/{sensor_id}/config",
            {
                "name": label,
                "unique_id": sensor_id,
                "icon": "mdi:battery-unknown",
                "state_topic": state_topic,
                "device": device,
            },
        )
        self._client.publish(state_topic, value, retain=True, qos=1)

    def _publish_json(self, topic: str, payload: dict) -> None:
        self._client.publish(topic, json.dumps(payload), retain=True, qos=1)


def build_ha_publisher(cfg: Config, conn) -> HomeAssistantPublisher | None:
    """None if Home Assistant/MQTT was never connected via the dashboard, or
    if the broker connection itself fails - a down/misconfigured broker must
    never break AirTag/owner-device polling, same philosophy as
    notifiers.build_notifiers()."""
    creds: MqttCredentials | None = get_mqtt_credentials(conn)
    if creds is None:
        return None
    password = keystore.decrypt(cfg.key_encryption_key, creds.password_encrypted) if creds.password_encrypted else None
    config = MqttConfig(host=creds.host, port=creds.port, username=creds.username, password=password, use_tls=creds.use_tls)
    try:
        return HomeAssistantPublisher(config)
    except Exception:
        logger.exception("Failed to connect to MQTT broker '%s:%d' for Home Assistant publishing.", creds.host, creds.port)
        return None
