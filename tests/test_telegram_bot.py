import datetime as dt
from unittest.mock import MagicMock, patch

from airtag_sentry import telegram_bot
from airtag_sentry.db import AirtagRecord, OwnerDevice, OwnerLocation, Report


def _make_airtags():
    return [
        AirtagRecord(id="a1", name="Rucksack"),
        AirtagRecord(id="a2", name="Fahrrad"),
    ]


def _make_owner_devices():
    return [
        OwnerDevice(id="d1", name="iPad", device_type="iPad", enabled=True, is_primary=False),
        OwnerDevice(id="d2", name="iPhone von Marius", device_type="iPhone", enabled=True, is_primary=True),
    ]


def _make_report(airtag_id: str, battery_level: str | None = None) -> Report:
    return Report(
        id=1,
        airtag_id=airtag_id,
        timestamp=dt.datetime(2026, 1, 1, 12, 0),
        lat=52.5,
        lon=13.4,
        accuracy=5.0,
        confidence=3,
        battery_level=battery_level,
    )


@patch("airtag_sentry.telegram_bot.list_owner_devices")
@patch("airtag_sentry.telegram_bot.list_airtags")
@patch("airtag_sentry.telegram_bot.requests.post")
def test_list_command_sends_numbered_airtags(mock_post, mock_list_airtags, mock_list_owner_devices):
    mock_post.return_value.raise_for_status = MagicMock()
    mock_list_airtags.return_value = _make_airtags()
    mock_list_owner_devices.return_value = []

    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={"message": {"chat": {"id": 111}, "text": "/list"}},
    )

    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.telegram.org/bottok/sendMessage"
    assert "1. Rucksack" in kwargs["json"]["text"]
    assert "2. Fahrrad" in kwargs["json"]["text"]


@patch("airtag_sentry.telegram_bot.list_owner_devices")
@patch("airtag_sentry.telegram_bot.list_airtags")
@patch("airtag_sentry.telegram_bot.requests.post")
def test_list_command_shows_devices_before_airtags(mock_post, mock_list_airtags, mock_list_owner_devices):
    mock_post.return_value.raise_for_status = MagicMock()
    mock_list_airtags.return_value = _make_airtags()
    mock_list_owner_devices.return_value = _make_owner_devices()

    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={"message": {"chat": {"id": 111}, "text": "/list"}},
    )

    text = mock_post.call_args.kwargs["json"]["text"]
    assert text.index("Deine Geräte:") < text.index("Deine AirTags:")
    # The primary device (own-location tracking) sorts first, matching
    # ObjectsList.tsx - not DB order (list_owner_devices orders by name).
    assert "1. ⭐ iPhone von Marius" in text
    assert "2. iPad" in text


@patch("airtag_sentry.telegram_bot.list_owner_devices")
@patch("airtag_sentry.telegram_bot.list_airtags")
@patch("airtag_sentry.telegram_bot.requests.post")
def test_message_from_unauthorized_chat_is_ignored(mock_post, mock_list_airtags, mock_list_owner_devices):
    mock_list_airtags.return_value = _make_airtags()
    mock_list_owner_devices.return_value = []

    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={"message": {"chat": {"id": 999}, "text": "/list"}},
    )

    mock_post.assert_not_called()


@patch("airtag_sentry.telegram_bot.list_owner_devices")
@patch("airtag_sentry.telegram_bot.list_airtags")
@patch("airtag_sentry.telegram_bot.requests.post")
def test_where_without_arg_sends_device_picker(mock_post, mock_list_airtags, mock_list_owner_devices):
    mock_post.return_value.raise_for_status = MagicMock()
    mock_list_airtags.return_value = _make_airtags()
    mock_list_owner_devices.return_value = []

    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={"message": {"chat": {"id": 111}, "text": "/where"}},
    )

    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.telegram.org/bottok/sendMessage"
    buttons = kwargs["json"]["reply_markup"]["inline_keyboard"]
    assert [row[0]["text"] for row in buttons] == ["Rucksack", "Fahrrad"]
    assert [row[0]["callback_data"] for row in buttons] == ["where:0", "where:1"]


@patch("airtag_sentry.telegram_bot.list_owner_devices")
@patch("airtag_sentry.telegram_bot.list_airtags")
@patch("airtag_sentry.telegram_bot.requests.post")
def test_where_without_arg_lists_devices_before_airtags(mock_post, mock_list_airtags, mock_list_owner_devices):
    mock_post.return_value.raise_for_status = MagicMock()
    mock_list_airtags.return_value = _make_airtags()
    mock_list_owner_devices.return_value = _make_owner_devices()

    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={"message": {"chat": {"id": 111}, "text": "/where"}},
    )

    buttons = mock_post.call_args.kwargs["json"]["reply_markup"]["inline_keyboard"]
    assert [row[0]["text"] for row in buttons] == ["⭐ iPhone von Marius", "iPad", "Rucksack", "Fahrrad"]
    assert [row[0]["callback_data"] for row in buttons] == ["where:0", "where:1", "where:2", "where:3"]


@patch("airtag_sentry.telegram_bot.reverse_geocode")
@patch("airtag_sentry.telegram_bot.list_owner_devices")
@patch("airtag_sentry.telegram_bot.fetch_reports")
@patch("airtag_sentry.telegram_bot.list_airtags")
@patch("airtag_sentry.telegram_bot.requests.post")
def test_where_with_unique_matching_name_sends_location(
    mock_post, mock_list_airtags, mock_fetch_reports, mock_list_owner_devices, mock_reverse_geocode
):
    mock_post.return_value.raise_for_status = MagicMock()
    mock_list_airtags.return_value = _make_airtags()
    mock_list_owner_devices.return_value = []
    mock_fetch_reports.return_value = [_make_report("a2")]
    mock_reverse_geocode.return_value = None

    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={"message": {"chat": {"id": 111}, "text": "/where fahrrad"}},
    )

    call_args = mock_fetch_reports.call_args
    assert call_args.args[1] == "a2"
    assert call_args.kwargs == {"limit": 1}

    args, kwargs = mock_post.call_args
    assert "52.5,13.4" in kwargs["json"]["text"]
    assert "reply_markup" not in kwargs["json"]


@patch("airtag_sentry.telegram_bot.reverse_geocode")
@patch("airtag_sentry.telegram_bot.list_owner_devices")
@patch("airtag_sentry.telegram_bot.fetch_reports")
@patch("airtag_sentry.telegram_bot.list_airtags")
@patch("airtag_sentry.telegram_bot.requests.post")
def test_where_location_includes_battery_and_address(
    mock_post, mock_list_airtags, mock_fetch_reports, mock_list_owner_devices, mock_reverse_geocode
):
    mock_post.return_value.raise_for_status = MagicMock()
    mock_list_airtags.return_value = _make_airtags()
    mock_list_owner_devices.return_value = []
    mock_fetch_reports.return_value = [_make_report("a2", battery_level="low")]
    mock_reverse_geocode.return_value = "Musterstraße 1, Berlin"

    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={"message": {"chat": {"id": 111}, "text": "/where fahrrad"}},
    )

    mock_reverse_geocode.assert_called_once_with(52.5, 13.4)
    text = mock_post.call_args.kwargs["json"]["text"]
    assert "Batterie: Niedrig" in text
    assert "Musterstraße 1, Berlin" in text


@patch("airtag_sentry.telegram_bot.list_owner_devices")
@patch("airtag_sentry.telegram_bot.list_airtags")
@patch("airtag_sentry.telegram_bot.requests.post")
def test_where_with_no_match_reports_not_found(mock_post, mock_list_airtags, mock_list_owner_devices):
    mock_post.return_value.raise_for_status = MagicMock()
    mock_list_airtags.return_value = _make_airtags()
    mock_list_owner_devices.return_value = []

    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={"message": {"chat": {"id": 111}, "text": "/where Schluessel"}},
    )

    args, kwargs = mock_post.call_args
    assert "Nichts gefunden" in kwargs["json"]["text"]


@patch("airtag_sentry.telegram_bot.reverse_geocode")
@patch("airtag_sentry.telegram_bot.fetch_owner_device_location_history")
@patch("airtag_sentry.telegram_bot.list_owner_devices")
@patch("airtag_sentry.telegram_bot.list_airtags")
@patch("airtag_sentry.telegram_bot.requests.post")
def test_where_with_unique_matching_device_name_sends_location(
    mock_post, mock_list_airtags, mock_list_owner_devices, mock_fetch_history, mock_reverse_geocode
):
    mock_post.return_value.raise_for_status = MagicMock()
    mock_list_airtags.return_value = _make_airtags()
    mock_list_owner_devices.return_value = _make_owner_devices()
    mock_fetch_history.return_value = [
        OwnerLocation(id=1, device_id="d1", recorded_at=dt.datetime(2026, 1, 1, 12, 0), lat=52.5, lon=13.4, horizontal_accuracy=5.0)
    ]
    mock_reverse_geocode.return_value = None

    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={"message": {"chat": {"id": 111}, "text": "/where ipad"}},
    )

    call_args = mock_fetch_history.call_args
    assert call_args.args[1] == "d1"
    assert call_args.kwargs == {"limit": 1}

    args, kwargs = mock_post.call_args
    assert "52.5,13.4" in kwargs["json"]["text"]
    assert "reply_markup" not in kwargs["json"]


@patch("airtag_sentry.telegram_bot.reverse_geocode")
@patch("airtag_sentry.telegram_bot.fetch_owner_device_location_history")
@patch("airtag_sentry.telegram_bot.list_owner_devices")
@patch("airtag_sentry.telegram_bot.list_airtags")
@patch("airtag_sentry.telegram_bot.requests.post")
def test_where_device_location_includes_battery(
    mock_post, mock_list_airtags, mock_list_owner_devices, mock_fetch_history, mock_reverse_geocode
):
    mock_post.return_value.raise_for_status = MagicMock()
    mock_list_airtags.return_value = _make_airtags()
    mock_list_owner_devices.return_value = _make_owner_devices()
    mock_fetch_history.return_value = [
        OwnerLocation(
            id=1,
            device_id="d1",
            recorded_at=dt.datetime(2026, 1, 1, 12, 0),
            lat=52.5,
            lon=13.4,
            horizontal_accuracy=5.0,
            battery_level=0.42,
            battery_status="Charging",
        )
    ]
    mock_reverse_geocode.return_value = None

    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={"message": {"chat": {"id": 111}, "text": "/where ipad"}},
    )

    text = mock_post.call_args.kwargs["json"]["text"]
    assert "Batterie: 42 % (lädt)" in text


@patch("airtag_sentry.telegram_bot.reverse_geocode")
@patch("airtag_sentry.telegram_bot.list_owner_devices")
@patch("airtag_sentry.telegram_bot.fetch_reports")
@patch("airtag_sentry.telegram_bot.list_airtags")
@patch("airtag_sentry.telegram_bot.requests.post")
def test_callback_query_resolves_picker_selection(
    mock_post, mock_list_airtags, mock_fetch_reports, mock_list_owner_devices, mock_reverse_geocode
):
    mock_post.return_value.raise_for_status = MagicMock()
    mock_list_airtags.return_value = _make_airtags()
    mock_list_owner_devices.return_value = []
    mock_fetch_reports.return_value = [_make_report("a2")]
    mock_reverse_geocode.return_value = None

    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={
            "callback_query": {
                "id": "cb1",
                "data": "where:1",
                "message": {"chat": {"id": 111}, "message_id": 42},
            }
        },
    )

    called_methods = [call.args[0] for call in mock_post.call_args_list]
    assert called_methods == [
        "https://api.telegram.org/bottok/answerCallbackQuery",
        "https://api.telegram.org/bottok/editMessageText",
    ]
    edit_kwargs = mock_post.call_args_list[1].kwargs
    assert "Fahrrad" in edit_kwargs["json"]["text"]


@patch("airtag_sentry.telegram_bot.requests.post")
def test_callback_query_from_unauthorized_chat_is_ignored(mock_post):
    telegram_bot.handle_update(
        conn=MagicMock(),
        bot_token="tok",
        chat_id="111",
        update={
            "callback_query": {
                "id": "cb1",
                "data": "where:0",
                "message": {"chat": {"id": 999}, "message_id": 42},
            }
        },
    )

    mock_post.assert_not_called()
