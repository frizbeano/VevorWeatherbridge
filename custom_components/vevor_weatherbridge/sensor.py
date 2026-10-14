"""Sensors for VEVOR Weatherbridge.

Values are reported in the units the station sends (imperial). Home Assistant
converts them to the user's unit system automatically, and each sensor's unit
can be changed in its entity settings.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UV_INDEX,
    EntityCategory,
    UnitOfIrradiance,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WeatherBridgeConfigEntry
from .const import DOMAIN, MANUFACTURER, MODEL
from .station import WeatherStation

LAST_UPDATE_KEY = "last_update"


def _temperature(key: str, *, enabled: bool = True) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=enabled,
    )


def _rain_total(key: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
    )


# Keyed by the lowercase Weather Underground query parameter.
SENSORS: dict[str, SensorEntityDescription] = {
    desc.key: desc
    for desc in (
        _temperature("tempf"),
        _temperature("indoortempf"),
        _temperature("dewptf"),
        _temperature("windchillf"),
        _temperature("heatindexf"),
        SensorEntityDescription(
            key="humidity",
            translation_key="humidity",
            device_class=SensorDeviceClass.HUMIDITY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
        ),
        SensorEntityDescription(
            key="indoorhumidity",
            translation_key="indoorhumidity",
            device_class=SensorDeviceClass.HUMIDITY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
        ),
        SensorEntityDescription(
            key="baromin",
            translation_key="baromin",
            device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            native_unit_of_measurement=UnitOfPressure.INHG,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        SensorEntityDescription(
            key="absbaromin",
            translation_key="absbaromin",
            device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            native_unit_of_measurement=UnitOfPressure.INHG,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        SensorEntityDescription(
            key="windspeedmph",
            translation_key="windspeedmph",
            device_class=SensorDeviceClass.WIND_SPEED,
            native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        SensorEntityDescription(
            key="windgustmph",
            translation_key="windgustmph",
            device_class=SensorDeviceClass.WIND_SPEED,
            native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        SensorEntityDescription(
            key="winddir",
            translation_key="winddir",
            device_class=SensorDeviceClass.WIND_DIRECTION,
            native_unit_of_measurement=DEGREE,
            state_class=SensorStateClass.MEASUREMENT_ANGLE,
            suggested_display_precision=0,
        ),
        SensorEntityDescription(
            key="rainin",
            translation_key="rainin",
            device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
            native_unit_of_measurement=UnitOfVolumetricFlux.INCHES_PER_HOUR,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
        ),
        _rain_total("dailyrainin"),
        _rain_total("weeklyrainin"),
        _rain_total("monthlyrainin"),
        _rain_total("yearlyrainin"),
        SensorEntityDescription(
            key="solarradiation",
            translation_key="solarradiation",
            device_class=SensorDeviceClass.IRRADIANCE,
            native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
        ),
        SensorEntityDescription(
            key="uv",
            translation_key="uv",
            native_unit_of_measurement=UV_INDEX,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
        ),
    )
}

LAST_UPDATE = SensorEntityDescription(
    key=LAST_UPDATE_KEY,
    translation_key=LAST_UPDATE_KEY,
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeatherBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors.

    Entities are created when the station first reports a value, since not
    every station model sends every field. Entities seen before are recreated
    at startup so they don't disappear until the next upload arrives.
    """
    station = entry.runtime_data
    known: set[str] = set()

    @callback
    def _async_add(keys: set[str]) -> None:
        new_keys = keys & SENSORS.keys() - known
        known.update(new_keys)
        async_add_entities(
            WeatherBridgeSensor(station, entry, SENSORS[key]) for key in sorted(new_keys)
        )

    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    _async_add(
        {
            reg_entry.unique_id.removeprefix(prefix)
            for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
        }
    )
    async_add_entities([WeatherBridgeSensor(station, entry, LAST_UPDATE)])

    @callback
    def _async_on_update() -> None:
        _async_add(set(station.data))

    entry.async_on_unload(async_dispatcher_connect(hass, station.signal_update, _async_on_update))


class WeatherBridgeSensor(SensorEntity):
    """A single weather station measurement."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        station: WeatherStation,
        entry: WeatherBridgeConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self._station = station
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def available(self) -> bool:
        """Return True if the station has reported this value recently."""
        if self.entity_description.key == LAST_UPDATE_KEY:
            return self._station.last_update is not None
        return self._station.available and self.entity_description.key in self._station.data

    @property
    def native_value(self) -> float | datetime | None:
        """Return the latest value."""
        if self.entity_description.key == LAST_UPDATE_KEY:
            return self._station.last_update
        return self._station.data.get(self.entity_description.key)

    async def async_added_to_hass(self) -> None:
        """Subscribe to station updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._station.signal_update, self.async_write_ha_state
            )
        )
