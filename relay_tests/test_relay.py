"""Tests for the standalone Docker/MQTT relay (weatherstation.py)."""

import json
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import weatherstation as ws

UPLOAD = (
    f"{ws.UPDATE_PATH}?ID=HOME1&PASSWORD=secret&dateutc=2026-10-14+12:00:00"
    "&tempf=68&humidity=55&baromin=29.92&windspeedmph=10&windgustmph=-9999"
    "&rainin=0.1&dailyrainin=1&solarradiation=100&UV=3"
)


@pytest.fixture
def mqtt_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Install a Publisher backed by a mock MQTT client."""
    client = MagicMock()
    with patch.object(ws.mqtt, "Client", return_value=client):
        monkeypatch.setattr(ws, "publisher", ws.Publisher())
    client.connect_async.assert_called_once_with(ws.MQTT_HOST, ws.MQTT_PORT, 60)
    return client


def _published(client: MagicMock) -> dict[str, str]:
    """Return the last payload published to each topic."""
    return {call.args[0]: call.args[1] for call in client.publish.call_args_list}


def _upload(path: str = UPLOAD) -> str:
    resp = ws.app.test_client().get(path)
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1.5", 1.5), ("-9999", None), ("", None), ("abc", None), ("nan", None), (None, None)],
)
def test_parse_value(raw: str | None, expected: float | None) -> None:
    assert ws.parse_value(raw) == expected


def test_upload_publishes_metric(mqtt_client: MagicMock) -> None:
    assert _upload().strip() == "success"
    published = _published(mqtt_client)
    base = f"{ws.MQTT_PREFIX}/sensor/{ws.DEVICE_ID}"

    assert published[f"{base}_temperature/state"] == "20.0"
    assert published[f"{base}_barometric_pressure/state"] == "1013.2"
    assert published[f"{base}_wind_speed/state"] == "16.1"
    assert published[f"{base}_rainfall/state"] == "2.54"
    assert published[f"{base}_solar_radiation/state"] == "100.0"
    # The -9999 sentinel is never published.
    assert f"{base}_wind_gust_speed/state" not in published

    config = json.loads(published[f"{base}_temperature/config"])
    assert config["unique_id"] == f"{ws.DEVICE_ID}_temperature"
    assert config["name"] == "Temperature"
    assert config["unit_of_measurement"] == "°C"
    assert config["state_class"] == "measurement"
    assert config["availability_topic"] == ws.AVAILABILITY_TOPIC

    rain = json.loads(published[f"{base}_rainfall/config"])
    assert rain["device_class"] == "precipitation_intensity"
    assert rain["unit_of_measurement"] == "mm/h"


def test_upload_imperial(mqtt_client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws, "METRIC", False)
    _upload()
    published = _published(mqtt_client)
    base = f"{ws.MQTT_PREFIX}/sensor/{ws.DEVICE_ID}"
    assert published[f"{base}_temperature/state"] == "68.0"
    assert json.loads(published[f"{base}_temperature/config"])["unit_of_measurement"] == "°F"


def test_discovery_announced_once(mqtt_client: MagicMock) -> None:
    _upload()
    _upload()
    config_topic = f"{ws.MQTT_PREFIX}/sensor/{ws.DEVICE_ID}_temperature/config"
    topics = [call.args[0] for call in mqtt_client.publish.call_args_list]
    assert topics.count(config_topic) == 1


def test_bad_values_still_succeed(mqtt_client: MagicMock) -> None:
    assert _upload(f"{ws.UPDATE_PATH}?tempf=abc&humidity=50").strip() == "success"
    topics = [call.args[0] for call in mqtt_client.publish.call_args_list]
    assert not any("temperature" in topic for topic in topics)
    assert any("humidity/state" in topic for topic in topics)


def _doh_response(address: str) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"Answer": [{"type": 1, "data": address}]}
    return resp


def test_forwarding(mqtt_client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws, "WU_FORWARD", True)
    monkeypatch.setattr(ws, "WU_USERNAME", "KXX1")
    wu_resp = MagicMock(status_code=200, text="success")
    with patch.object(ws.requests, "get", side_effect=[_doh_response("34.0.0.1"), wu_resp]) as get:
        _upload()

    url = get.call_args.args[0]
    assert url == f"http://34.0.0.1{ws.UPDATE_PATH}"
    assert get.call_args.kwargs["headers"] == {"Host": ws.WU_HOST}
    assert get.call_args.kwargs["params"]["ID"] == "KXX1"
    assert get.call_args.kwargs["params"]["PASSWORD"] == "secret"


def test_forwarding_refuses_private_address(
    mqtt_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ws, "WU_FORWARD", True)
    with patch.object(ws.requests, "get", return_value=_doh_response("192.168.0.36")) as get:
        _upload()
    # Only the DNS-over-HTTPS lookups happen; nothing is sent to the private address.
    assert get.call_count == len(ws.WU_DOH_URLS)
    assert all("dns" in call.args[0] for call in get.call_args_list)
