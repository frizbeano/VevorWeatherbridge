"""Receive Weather Underground protocol uploads from the station."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import logging
import math

from aiohttp import ClientError, ClientSession, ClientTimeout, TCPConnector, web
from aiohttp.resolver import AsyncResolver

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import (
    SECRET_PARAMS,
    STALE_AFTER,
    UPDATE_PATH,
    WU_NAMESERVERS,
    WU_TIMEOUT,
    WU_URL,
)

_LOGGER = logging.getLogger(__name__)

# Weather Underground uses -9999 to mean "no reading".
_MISSING_VALUE = -9999


def parse_value(raw: str | None) -> float | None:
    """Convert a raw query value to a float, or None if missing or invalid."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value) or value <= _MISSING_VALUE:
        return None
    return value


def parse_dateutc(raw: str | None) -> datetime:
    """Parse the station's `dateutc` field, falling back to now."""
    if raw and raw.lower() != "now":
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
        else:
            return parsed.replace(tzinfo=dt_util.UTC)
    return dt_util.utcnow()


class WeatherStation:
    """State for one station: listens for uploads and notifies entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        port: int,
        station_id: str | None,
    ) -> None:
        """Initialize the station."""
        self.hass = hass
        self.port = port
        self.station_id = station_id
        self.signal_update = f"vevor_weatherbridge_update_{entry_id}"
        self.data: dict[str, float] = {}
        self.last_update: datetime | None = None
        self.last_params: dict[str, str] = {}
        self.software: str | None = None
        self.forwarder: WundergroundForwarder | None = None
        self._runner: web.AppRunner | None = None
        self._stale_unsub: CALLBACK_TYPE | None = None

    @property
    def available(self) -> bool:
        """Return True if the station reported recently."""
        return self.last_update is not None and dt_util.utcnow() - self.last_update < STALE_AFTER

    async def async_start(self) -> None:
        """Start the HTTP listener the station uploads to."""
        app = web.Application()
        app.router.add_get(UPDATE_PATH, self._handle_request)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        try:
            await web.TCPSite(runner, port=self.port).start()
        except OSError:
            await runner.cleanup()
            raise
        self._runner = runner

    async def async_stop(self) -> None:
        """Stop the listener and pending timers."""
        if self._stale_unsub:
            self._stale_unsub()
            self._stale_unsub = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        if self.forwarder:
            await self.forwarder.async_close()

    async def _handle_request(self, request: web.Request) -> web.Response:
        """Handle an upload. Always answer `success` so the station never retries."""
        self.async_process_upload(request.query)
        return web.Response(text="success\n")

    @callback
    def async_process_upload(self, query: Mapping[str, str]) -> None:
        """Parse an upload, update state and notify entities."""
        params = {key.lower(): value for key, value in query.items()}

        if self.station_id and params.get("id") != self.station_id:
            _LOGGER.debug("Ignoring upload from unexpected station %s", params.get("id"))
            return

        self.data = {
            key: value
            for key, raw in params.items()
            if key not in SECRET_PARAMS and (value := parse_value(raw)) is not None
        }
        self.last_update = parse_dateutc(params.get("dateutc"))
        self.last_params = {k: v for k, v in params.items() if k not in SECRET_PARAMS}
        self.software = params.get("softwaretype", self.software)

        if self._stale_unsub:
            self._stale_unsub()
        self._stale_unsub = async_call_later(self.hass, STALE_AFTER, self._async_mark_stale)
        async_dispatcher_send(self.hass, self.signal_update)

        if self.forwarder:
            self.hass.async_create_background_task(
                self.forwarder.async_forward(query), "vevor_weatherbridge_wu_forward"
            )

    @callback
    def _async_mark_stale(self, _now: datetime) -> None:
        """Let entities re-evaluate availability once the data is stale."""
        self._stale_unsub = None
        async_dispatcher_send(self.hass, self.signal_update)


class WundergroundForwarder:
    """Forward uploads to Weather Underground.

    Uses its own session with a resolver pointed at public DNS: the local DNS
    normally redirects the Weather Underground hostname back to Home Assistant,
    which would loop the upload back to ourselves.
    """

    def __init__(self, station_id: str | None, station_key: str | None) -> None:
        """Initialize the forwarder."""
        self._station_id = station_id
        self._station_key = station_key
        self._session: ClientSession | None = None

    async def async_forward(self, query: Mapping[str, str]) -> None:
        """Send one upload to Weather Underground."""
        params = dict(query)
        if self._station_id:
            params["ID"] = self._station_id
        if self._station_key:
            params["PASSWORD"] = self._station_key

        if self._session is None:
            self._session = ClientSession(
                connector=TCPConnector(resolver=AsyncResolver(nameservers=WU_NAMESERVERS)),
                timeout=ClientTimeout(total=WU_TIMEOUT),
            )
        try:
            async with self._session.get(WU_URL, params=params) as resp:
                body = (await resp.text()).strip()
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning("Failed to forward to Weather Underground: %s", err)
            return
        if resp.status != 200 or body.lower() != "success":
            _LOGGER.warning(
                "Weather Underground rejected the upload (HTTP %s): %s",
                resp.status,
                body[:200],
            )

    async def async_close(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
