"""Tests for diagnostics."""

from aiohttp import ClientSession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vevor_weatherbridge.const import (
    CONF_STATION_ID,
    CONF_WU_FORWARD,
    CONF_WU_STATION_KEY,
    DOMAIN,
    UPDATE_PATH,
)
from custom_components.vevor_weatherbridge.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.components.diagnostics import REDACTED
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant


async def test_diagnostics_redacts_secrets(hass: HomeAssistant, free_port: int) -> None:
    """Test diagnostics include the last upload without credentials."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Backyard",
        unique_id=str(free_port),
        data={CONF_PORT: free_port, CONF_STATION_ID: "HOME1"},
        options={CONF_WU_FORWARD: False, CONF_WU_STATION_KEY: "wu-secret"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async with ClientSession() as session:
        params = {"ID": "HOME1", "PASSWORD": "pw", "tempf": "68", "softwaretype": "fw1"}
        async with session.get(f"http://127.0.0.1:{free_port}{UPDATE_PATH}", params=params):
            pass
        async with session.get(f"http://127.0.0.1:{free_port}/other"):
            pass

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["data"] == {CONF_PORT: free_port, CONF_STATION_ID: REDACTED}
    assert diag["options"][CONF_WU_STATION_KEY] == REDACTED
    assert diag["available"] is True
    assert diag["software"] == "fw1"
    assert diag["last_upload"] == {"tempf": "68", "softwaretype": "fw1"}
    assert [r["path"] for r in diag["unrecognized_requests"]] == ["/other"]
    assert "pw" not in str(diag) and "wu-secret" not in str(diag)
