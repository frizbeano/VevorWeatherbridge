"""Tests for receiving uploads end to end."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.vevor_weatherbridge.const import (
    CONF_STATION_ID,
    CONF_WU_FORWARD,
    CONF_WU_STATION_ID,
    UPDATE_PATH,
    WU_DOH_URLS,
    WU_HOST,
)
from custom_components.vevor_weatherbridge.station import (
    WundergroundForwarder,
    parse_value,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PORT, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

UPLOAD = {
    "ID": "ABC123",
    "PASSWORD": "hunter2",
    "dateutc": "2026-10-14 12:00:00",
    "tempf": "68.0",
    "dewptf": "50.0",
    "humidity": "55",
    "baromin": "29.92",
    "windspeedmph": "10",
    "windgustmph": "-9999",
    "winddir": "270",
    "rainin": "0.10",
    "dailyrainin": "1.00",
    "solarradiation": "123.4",
    "UV": "3",
    "softwaretype": "EasyWeatherPro_V5.1.6",
    "action": "updateraw",
}


async def _upload(port: int, params: dict[str, str]) -> str:
    async with (
        ClientSession() as session,
        session.get(f"http://127.0.0.1:{port}{UPDATE_PATH}", params=params) as resp,
    ):
        assert resp.status == 200
        return await resp.text()


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_upload_creates_sensors(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """Test an upload creates sensors converted to the metric unit system."""
    freezer.move_to("2026-10-14 12:00:30+00:00")
    await _setup(hass, mock_config_entry)

    assert hass.states.get("sensor.backyard_temperature") is None
    assert hass.states.get("sensor.backyard_last_update").state == STATE_UNAVAILABLE

    assert (await _upload(mock_config_entry.data[CONF_PORT], UPLOAD)).strip() == "success"
    await hass.async_block_till_done()

    def value(entity_id: str) -> float:
        return float(hass.states.get(entity_id).state)

    assert value("sensor.backyard_temperature") == pytest.approx(20.0)
    assert hass.states.get("sensor.backyard_temperature").attributes["unit_of_measurement"] == "°C"
    assert value("sensor.backyard_dew_point") == pytest.approx(10.0)
    assert value("sensor.backyard_humidity") == 55
    assert value("sensor.backyard_relative_pressure") == pytest.approx(1013.2, abs=0.1)
    assert value("sensor.backyard_wind_speed") == pytest.approx(16.09, abs=0.01)
    assert value("sensor.backyard_wind_direction") == 270
    assert value("sensor.backyard_rain_rate") == pytest.approx(2.54)
    assert value("sensor.backyard_daily_rain") == pytest.approx(25.4)
    assert value("sensor.backyard_solar_radiation") == pytest.approx(123.4)
    assert value("sensor.backyard_uv_index") == 3
    assert hass.states.get("sensor.backyard_last_update").state == "2026-10-14T12:00:00+00:00"
    # Missing (-9999) values never create an entity.
    assert hass.states.get("sensor.backyard_wind_gust") is None


async def test_bad_values_ignored(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """Test garbage values don't break the upload."""
    await _setup(hass, mock_config_entry)
    text = await _upload(
        mock_config_entry.data[CONF_PORT], {"tempf": "abc", "humidity": "nan", "dateutc": "bogus"}
    )
    assert text.strip() == "success"
    await hass.async_block_till_done()
    assert hass.states.get("sensor.backyard_temperature") is None
    assert hass.states.get("sensor.backyard_last_update").state != STATE_UNAVAILABLE


async def test_post_and_path_variants(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test uploads sent with POST or a different path case are accepted."""
    await _setup(hass, mock_config_entry)
    port = mock_config_entry.data[CONF_PORT]
    async with (
        ClientSession() as session,
        session.post(
            f"http://127.0.0.1:{port}/WeatherStation/UpdateWeatherStation.php",
            data={"tempf": "68", "dateutc": "now"},
        ) as resp,
    ):
        assert resp.status == 200
        assert (await resp.text()).strip() == "success"
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.backyard_temperature").state) == pytest.approx(20.0)


async def test_unrecognized_request_logged(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, caplog: pytest.LogCaptureFixture
) -> None:
    """Test requests that aren't uploads are logged once and kept for diagnostics."""
    await _setup(hass, mock_config_entry)
    port = mock_config_entry.data[CONF_PORT]
    async with ClientSession() as session:
        for _ in range(2):
            async with session.get(f"http://127.0.0.1:{port}/data/report/") as resp:
                assert resp.status == 404

    assert caplog.text.count("Received GET /data/report/") == 1
    requests = mock_config_entry.runtime_data.unrecognized_requests
    assert [r["path"] for r in requests] == ["/data/report/", "/data/report/"]


async def test_station_id_filter(hass: HomeAssistant, free_port: int) -> None:
    """Test uploads from other stations are ignored."""
    entry = MockConfigEntry(
        domain="vevor_weatherbridge",
        title="Backyard",
        unique_id=str(free_port),
        data={CONF_PORT: free_port, CONF_STATION_ID: "OTHER"},
    )
    await _setup(hass, entry)
    await _upload(free_port, UPLOAD)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.backyard_temperature") is None

    await _upload(free_port, {**UPLOAD, "ID": "OTHER"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.backyard_temperature") is not None


async def test_stale_and_restore(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """Test sensors go unavailable when stale and survive a reload."""
    freezer.move_to("2026-10-14 12:00:30+00:00")
    await _setup(hass, mock_config_entry)
    await _upload(mock_config_entry.data[CONF_PORT], UPLOAD)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.backyard_temperature").state != STATE_UNAVAILABLE

    freezer.tick(timedelta(minutes=16))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.backyard_temperature").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.backyard_last_update").state != STATE_UNAVAILABLE

    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.backyard_temperature").state == STATE_UNAVAILABLE


async def test_unload_frees_port(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """Test unloading stops the listener so the port can be reused."""
    await _setup(hass, mock_config_entry)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_port_in_use_retries(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """Test setup is retried if the port is taken."""
    with patch(
        "custom_components.vevor_weatherbridge.station.web.TCPSite.start",
        side_effect=OSError("in use"),
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_forwarding(hass: HomeAssistant, free_port: int) -> None:
    """Test uploads are forwarded to Weather Underground when enabled."""
    entry = MockConfigEntry(
        domain="vevor_weatherbridge",
        title="Backyard",
        unique_id=str(free_port),
        data={CONF_PORT: free_port},
        options={CONF_WU_FORWARD: True, CONF_WU_STATION_ID: "KXX1"},
    )
    with patch.object(WundergroundForwarder, "async_forward", AsyncMock()) as forward:
        await _setup(hass, entry)
        await _upload(free_port, UPLOAD)
        await hass.async_block_till_done()
    forward.assert_awaited_once()
    # The original query, including credentials, is what gets forwarded.
    assert forward.call_args.args[0]["PASSWORD"] == "hunter2"


def _doh_answer(address: str) -> dict:
    return {"Status": 0, "Answer": [{"name": WU_HOST, "type": 1, "TTL": 60, "data": address}]}


async def test_forwarder_overrides_credentials(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test uploads go to the DNS-over-HTTPS address with configured credentials."""
    aioclient_mock.get(WU_DOH_URLS[0], json=_doh_answer("34.0.0.1"))
    aioclient_mock.get(f"http://34.0.0.1{UPDATE_PATH}", text="success")
    forwarder = WundergroundForwarder(async_get_clientsession(hass), "KXX1", "key")

    await forwarder.async_forward({"ID": "ABC", "PASSWORD": "pw", "tempf": "1"})
    await forwarder.async_forward({"ID": "ABC", "PASSWORD": "pw", "tempf": "2"})

    # The address is cached, so DNS is only queried once.
    calls = [call for call in aioclient_mock.mock_calls if call[1].host == "34.0.0.1"]
    assert aioclient_mock.call_count == 3
    _method, url, _data, headers = calls[0]
    assert dict(url.query) == {"ID": "KXX1", "PASSWORD": "key", "tempf": "1"}
    assert headers["Host"] == WU_HOST


async def test_forwarder_refuses_private_address(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a hijacked lookup pointing at the LAN is never used."""
    for url in WU_DOH_URLS:
        aioclient_mock.get(url, json=_doh_answer("192.168.0.36"))
    forwarder = WundergroundForwarder(async_get_clientsession(hass), None, None)

    await forwarder.async_forward({"tempf": "1"})

    assert aioclient_mock.call_count == len(WU_DOH_URLS)
    assert "could not look up a public address" in caplog.text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1.5", 1.5), ("-9999", None), ("", None), ("inf", None), (None, None), ("-5", -5.0)],
)
def test_parse_value(raw: str | None, expected: float | None) -> None:
    """Test value parsing."""
    assert parse_value(raw) == expected
