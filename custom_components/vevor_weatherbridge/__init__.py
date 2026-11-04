"""The VEVOR Weatherbridge integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_STATION_ADDRESS,
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
        entry.data.get(CONF_STATION_ADDRESS) or None,
    )
    # Forwarding sends uploads to Weather Underground under the user's key, so
    # it only runs once uploads are restricted to the station's own address.
    issue_id = f"forwarding_needs_station_address_{entry.entry_id}"
    if entry.options.get(CONF_WU_FORWARD) and station.station_address is None:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="forwarding_needs_station_address",
            translation_placeholders={"name": entry.title},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
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


async def async_remove_entry(hass: HomeAssistant, entry: WeatherBridgeConfigEntry) -> None:
    """Remove any repair issue left by the entry."""
    ir.async_delete_issue(hass, DOMAIN, f"forwarding_needs_station_address_{entry.entry_id}")


async def _async_update_listener(hass: HomeAssistant, entry: WeatherBridgeConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
