"""Tests for the config flow's port check."""

import socket

from custom_components.vevor_weatherbridge.config_flow import check_port


def test_check_port(free_port: int) -> None:
    """Test the port check detects a port that's already taken."""
    assert check_port(free_port) is None
    with socket.socket() as sock:
        sock.bind(("", free_port))
        sock.listen()
        assert check_port(free_port) == "port_in_use"
