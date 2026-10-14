"""Config flow for VEVOR Weatherbridge."""

from __future__ import annotations

import socket
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, selector

from .const import (
    CONF_STATION_ID,
    CONF_WU_FORWARD,
    CONF_WU_STATION_ID,
    CONF_WU_STATION_KEY,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)


def check_port(port: int) -> str | None:
    """Return an error key if the port cannot be listened on."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", port))
        except PermissionError:
            return "port_permission"
        except OSError:
            return "port_in_use"
    return None


def _connection_schema(defaults: dict[str, Any]) -> dict[vol.Marker, Any]:
    return {
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): cv.port,
        vol.Optional(
            CONF_STATION_ID,
            description={"suggested_value": defaults.get(CONF_STATION_ID)},
        ): str,
    }


class WeatherBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VEVOR Weatherbridge."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_PORT]
            await self.async_set_unique_id(str(port))
            self._abort_if_unique_id_configured()
            if error := await self.hass.async_add_executor_job(check_port, port):
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_PORT: port,
                        CONF_STATION_ID: user_input.get(CONF_STATION_ID, "").strip(),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                **_connection_schema(user_input or {}),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the listening port or station filter."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_PORT]
            if port != entry.data[CONF_PORT]:
                await self.async_set_unique_id(str(port))
                self._abort_if_unique_id_configured()
                if error := await self.hass.async_add_executor_job(check_port, port):
                    errors["base"] = error
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=str(port),
                    data_updates={
                        CONF_PORT: port,
                        CONF_STATION_ID: user_input.get(CONF_STATION_ID, "").strip(),
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(_connection_schema(user_input or dict(entry.data))),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WeatherBridgeOptionsFlow:
        """Get the options flow."""
        return WeatherBridgeOptionsFlow()


class WeatherBridgeOptionsFlow(OptionsFlow):
    """Weather Underground forwarding options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_WU_FORWARD, default=options.get(CONF_WU_FORWARD, False)): bool,
                vol.Optional(
                    CONF_WU_STATION_ID,
                    description={"suggested_value": options.get(CONF_WU_STATION_ID)},
                ): str,
                vol.Optional(
                    CONF_WU_STATION_KEY,
                    description={"suggested_value": options.get(CONF_WU_STATION_KEY)},
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
