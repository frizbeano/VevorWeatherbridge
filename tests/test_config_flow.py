"""Tests for the config flow."""

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vevor_weatherbridge.const import (
    CONF_STATION_ID,
    CONF_WU_FORWARD,
    CONF_WU_STATION_ID,
    CONF_WU_STATION_KEY,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

pytestmark = pytest.mark.usefixtures("mock_check_port")


async def test_user_flow(hass: HomeAssistant) -> None:
    """Test creating an entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    with patch("custom_components.vevor_weatherbridge.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Backyard", CONF_PORT: 8080, CONF_STATION_ID: " ABC123 "},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Backyard"
    assert result["data"] == {CONF_PORT: 8080, CONF_STATION_ID: "ABC123"}
    assert result["result"].unique_id == "8080"


async def test_user_flow_port_error(hass: HomeAssistant, mock_check_port) -> None:
    """Test an unusable port shows an error and can recover."""
    mock_check_port.return_value = "port_in_use"
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Backyard", CONF_PORT: 80}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "port_in_use"}

    mock_check_port.return_value = None
    with patch("custom_components.vevor_weatherbridge.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "Backyard", CONF_PORT: 80}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_duplicate_port(hass: HomeAssistant) -> None:
    """Test a second station on the same port is rejected."""
    MockConfigEntry(domain=DOMAIN, unique_id="80", data={CONF_PORT: 80}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Backyard", CONF_PORT: 80}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure(hass: HomeAssistant) -> None:
    """Test changing the port."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="80", data={CONF_PORT: 80, CONF_STATION_ID: ""}
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM

    with patch("custom_components.vevor_weatherbridge.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PORT: 8080, CONF_STATION_ID: "XYZ"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "8080"
    assert entry.data == {CONF_PORT: 8080, CONF_STATION_ID: "XYZ"}


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test configuring Weather Underground forwarding."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="80", data={CONF_PORT: 80})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    options = {CONF_WU_FORWARD: True, CONF_WU_STATION_ID: "KXX1", CONF_WU_STATION_KEY: "secret"}
    with patch("custom_components.vevor_weatherbridge.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(result["flow_id"], options)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == options
