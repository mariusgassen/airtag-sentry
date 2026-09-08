"""Inbound Telegram bot commands (/list, /where, /help).

Outbound alert notifications go through notifiers/telegram.py; this module is
the other direction - Telegram POSTs an Update to our webhook (see
web/app.py's /api/telegram/webhook) and we reply via the Bot API directly.

Single-user app: every handler is gated on the update's chat id matching the
one configured chat_id *before* it touches any data or sends any reply - a
stranger who finds/adds the bot elsewhere gets silence, not even an error
message that would confirm the bot exists. Don't add a code path that
replies without going through that check first.
"""

from __future__ import annotations

import logging

import requests

from airtag_sentry.db import (
    AirtagRecord,
    OwnerDevice,
    Report,
    fetch_owner_device_location_history,
    fetch_reports,
    list_airtags,
    list_owner_devices,
)

logger = logging.getLogger(__name__)

_API_TIMEOUT = 10

_HELP_TEXT = (
    "Verfügbare Befehle:\n"
    "/list – alle Geräte und AirTags anzeigen\n"
    "/where [Name] – letzten Standort eines Geräts oder AirTags anzeigen "
    "(ohne Namen: Auswahl zum Antippen)"
)

# A /where target is either an owner device or an AirTag - see CLAUDE.md's
# "AirTags and owner devices get the same user-facing features" constraint.
_WhereItem = tuple[str, OwnerDevice] | tuple[str, AirtagRecord]


def _api_url(bot_token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{bot_token}/{method}"


def _send_message(bot_token: str, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    requests.post(_api_url(bot_token, "sendMessage"), json=payload, timeout=_API_TIMEOUT).raise_for_status()


def _edit_message(bot_token: str, chat_id: str, message_id: int, text: str) -> None:
    requests.post(
        _api_url(bot_token, "editMessageText"),
        json={"chat_id": chat_id, "message_id": message_id, "text": text},
        timeout=_API_TIMEOUT,
    ).raise_for_status()


def _answer_callback_query(bot_token: str, callback_query_id: str) -> None:
    requests.post(
        _api_url(bot_token, "answerCallbackQuery"),
        json={"callback_query_id": callback_query_id},
        timeout=_API_TIMEOUT,
    ).raise_for_status()


def set_webhook(bot_token: str, url: str, secret: str) -> None:
    """Register the webhook and the /-command autocomplete menu. Called once
    from the dashboard's "enable bot commands" action."""
    requests.post(
        _api_url(bot_token, "setWebhook"),
        json={"url": url, "secret_token": secret},
        timeout=_API_TIMEOUT,
    ).raise_for_status()
    requests.post(
        _api_url(bot_token, "setMyCommands"),
        json={
            "commands": [
                {"command": "list", "description": "Alle Geräte und AirTags anzeigen"},
                {"command": "where", "description": "Standort eines Geräts oder AirTags anzeigen"},
                {"command": "help", "description": "Verfügbare Befehle anzeigen"},
            ]
        },
        timeout=_API_TIMEOUT,
    ).raise_for_status()


def delete_webhook(bot_token: str) -> None:
    requests.post(_api_url(bot_token, "deleteWebhook"), timeout=_API_TIMEOUT).raise_for_status()


def handle_update(conn, bot_token: str, chat_id: str, update: dict) -> None:
    """Route one Telegram Update to the right handler. Never raises for
    malformed/unexpected updates - the webhook route responds 200 to Telegram
    either way, so this just logs and returns on anything unusable."""
    message = update.get("message")
    callback_query = update.get("callback_query")

    if message is not None:
        _handle_message(conn, bot_token, chat_id, message)
    elif callback_query is not None:
        _handle_callback_query(conn, bot_token, chat_id, callback_query)


def _is_authorized_chat(chat_id: str, candidate) -> bool:
    return candidate is not None and str(candidate) == str(chat_id)


def _handle_message(conn, bot_token: str, chat_id: str, message: dict) -> None:
    if not _is_authorized_chat(chat_id, message.get("chat", {}).get("id")):
        return
    text = (message.get("text") or "").strip()
    if not text.startswith("/"):
        return

    command, _, arg = text.partition(" ")
    command = command.split("@", 1)[0].lower()  # strip "@BotName" (used when addressing a bot in a group)
    arg = arg.strip()

    if command in ("/help", "/start"):
        _send_message(bot_token, chat_id, _HELP_TEXT)
    elif command == "/list":
        devices = [d for d in list_owner_devices(conn) if d.enabled]
        _send_message(bot_token, chat_id, _format_list(devices, list_airtags(conn)))
    elif command == "/where":
        _handle_where(conn, bot_token, chat_id, arg)
    else:
        _send_message(bot_token, chat_id, f"Unbekannter Befehl: {command}\n\n{_HELP_TEXT}")


def _format_list(devices: list[OwnerDevice], airtags: list[AirtagRecord]) -> str:
    """Owner devices (self-location tracking) listed first, in their own section,
    ahead of AirTags - see tasks/todo.md for the bugfix that added devices here at
    all (this command originally only knew about AirTags). Within that section,
    the primary device (the one answer to "where am I") sorts first, matching the
    dashboard's ObjectsList.tsx."""
    if not devices and not airtags:
        return "Keine Geräte oder AirTags konfiguriert."

    sections = []
    if devices:
        ordered = sorted(devices, key=lambda d: not d.is_primary)
        lines = [f"{i + 1}. {'⭐ ' if d.is_primary else ''}{d.display_name or d.name}" for i, d in enumerate(ordered)]
        sections.append("Deine Geräte:\n" + "\n".join(lines))
    if airtags:
        lines = [f"{i + 1}. {a.name}" for i, a in enumerate(airtags)]
        sections.append("Deine AirTags:\n" + "\n".join(lines))
    return "\n\n".join(sections)


def _where_items(conn) -> list[_WhereItem]:
    """Devices (primary first) then AirTags - same ordering as /list's
    _format_list, so the picker and search match what /list shows."""
    devices = sorted((d for d in list_owner_devices(conn) if d.enabled), key=lambda d: not d.is_primary)
    airtags = list_airtags(conn)
    return [("device", d) for d in devices] + [("airtag", a) for a in airtags]


def _item_name(item: _WhereItem) -> str:
    kind, obj = item
    return (obj.display_name or obj.name) if kind == "device" else obj.name


def _item_button_label(item: _WhereItem) -> str:
    kind, obj = item
    name = _item_name(item)
    return f"⭐ {name}" if kind == "device" and obj.is_primary else name


def _handle_where(conn, bot_token: str, chat_id: str, arg: str) -> None:
    items = _where_items(conn)
    if not items:
        _send_message(bot_token, chat_id, "Keine Geräte oder AirTags konfiguriert.")
        return

    if not arg:
        _send_picker(bot_token, chat_id, "Welches Gerät oder AirTag?", list(enumerate(items)))
        return

    query = arg.lower()
    matches = [(i, item) for i, item in enumerate(items) if query in _item_name(item).lower()]
    if not matches:
        _send_message(bot_token, chat_id, f"Nichts gefunden für „{arg}“. /list zeigt alle an.")
    elif len(matches) == 1:
        _send_message(bot_token, chat_id, _format_location(matches[0][1], conn))
    else:
        _send_picker(bot_token, chat_id, f"Mehrere Treffer für „{arg}“ – welches Gerät oder AirTag?", matches)


def _send_picker(bot_token: str, chat_id: str, prompt: str, indexed_items: list[tuple[int, _WhereItem]]) -> None:
    buttons = [[{"text": _item_button_label(item), "callback_data": f"where:{index}"}] for index, item in indexed_items]
    _send_message(bot_token, chat_id, prompt, reply_markup={"inline_keyboard": buttons})


def _format_location(item: _WhereItem, conn) -> str:
    kind, obj = item
    if kind == "device":
        name = obj.display_name or obj.name
        history = fetch_owner_device_location_history(conn, obj.id, limit=1)
        if not history:
            return f"{name}: noch kein Standort bekannt."
        location = history[0]  # newest-first, unlike fetch_reports
        maps_url = f"https://maps.google.com/?q={location.lat},{location.lon}"
        timestamp = location.recorded_at.strftime("%d.%m.%Y %H:%M")
        return f"{name}\n{timestamp}\n{maps_url}"

    airtag = obj
    reports: list[Report] = fetch_reports(conn, airtag.id, limit=1)
    if not reports:
        return f"{airtag.name}: noch kein Standort bekannt."
    report = reports[-1]
    maps_url = f"https://maps.google.com/?q={report.lat},{report.lon}"
    timestamp = report.timestamp.strftime("%d.%m.%Y %H:%M")
    return f"{airtag.name}\n{timestamp}\n{maps_url}"


def _handle_callback_query(conn, bot_token: str, chat_id: str, callback_query: dict) -> None:
    message = callback_query.get("message") or {}
    callback_id = callback_query.get("id")
    if not _is_authorized_chat(chat_id, message.get("chat", {}).get("id")):
        return

    command, _, index_str = (callback_query.get("data") or "").partition(":")
    if command != "where":
        if callback_id:
            _answer_callback_query(bot_token, callback_id)
        return

    items = _where_items(conn)
    try:
        item = items[int(index_str)]
    except (ValueError, IndexError):
        if callback_id:
            _answer_callback_query(bot_token, callback_id)
        return

    text = _format_location(item, conn)
    if callback_id:
        _answer_callback_query(bot_token, callback_id)
    message_id = message.get("message_id")
    if message_id is not None:
        _edit_message(bot_token, chat_id, message_id, text)
    else:
        _send_message(bot_token, chat_id, text)
