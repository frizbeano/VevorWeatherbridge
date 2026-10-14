"""Fixtures for VEVOR Weatherbridge tests."""

from collections.abc import Generator
import socket
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vevor_weatherbridge.const import CONF_STATION_ID, DOMAIN
from homeassistant.const import CONF_PORT


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in all tests."""


@pytest.fixture
def free_port(socket_enabled: None) -> int:
    """Return a free TCP port and allow real sockets for the test."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def mock_config_entry(free_port: int) -> MockConfigEntry:
    """Return a config entry listening on a free port."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Backyard",
        unique_id=str(free_port),
        data={CONF_PORT: free_port, CONF_STATION_ID: ""},
    )


@pytest.fixture
def mock_check_port() -> Generator[None]:
    """Pretend every port is free in config flow tests."""
    with patch(
        "custom_components.vevor_weatherbridge.config_flow.check_port", return_value=None
    ) as mock:
        yield mock
