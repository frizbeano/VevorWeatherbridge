"""The VEVOR Weatherbridge integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_STATION_ID,
    CONF_WU_FORWARD,
    CONF_WU_STATION_ID,
    CONF_WU_STATION_KEY,
    DOMAIN,
)
from .station import WeatherStation, WundergroundForwarder

PLATFORMS: list[Platform] = [Platform.SENSOR]

type WeatherBridgeConfigEntry = ConfigEntry[WeatherStation]


async def async_setup_entry(hass: HomeAssistant, entry: WeatherBridgeConfigEntry) -> bool:
    """Set up VEVOR Weatherbridge from a config entry."""
    station = WeatherStation(
        hass,
        entry.entry_id,
        entry.data[CONF_PORT],
        entry.data.get(CONF_STATION_ID) or None,
    )
    if entry.options.get(CONF_WU_FORWARD):
        station.forwarder = WundergroundForwarder(
            async_get_clientsession(hass),
            entry.options.get(CONF_WU_STATION_ID) or None,
            entry.options.get(CONF_WU_STATION_KEY) or None,
        )

    try:
        await station.async_start()
    except OSError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_listen",
            translation_placeholders={"port": str(station.port), "error": str(err)},
        ) from err

    entry.runtime_data = station
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WeatherBridgeConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: WeatherBridgeConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
