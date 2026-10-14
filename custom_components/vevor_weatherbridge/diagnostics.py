"""Diagnostics support for VEVOR Weatherbridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import WeatherBridgeConfigEntry
from .const import CONF_STATION_ID, CONF_WU_STATION_ID, CONF_WU_STATION_KEY

TO_REDACT = {CONF_STATION_ID, CONF_WU_STATION_ID, CONF_WU_STATION_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WeatherBridgeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    station = entry.runtime_data
    return {
        "data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": async_redact_data(dict(entry.options), TO_REDACT),
        "available": station.available,
        "last_update": station.last_update,
        "software": station.software,
        "last_upload": station.last_params,
        "unrecognized_requests": list(station.unrecognized_requests),
    }
