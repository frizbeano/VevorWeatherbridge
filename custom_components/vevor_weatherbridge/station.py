"""Receive Weather Underground protocol uploads from the station."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from datetime import datetime
import ipaddress
import logging
import math
import time

from aiohttp import ClientError, ClientSession, ClientTimeout, web

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import (
    SECRET_PARAMS,
    STALE_AFTER,
    UPDATE_PATH,
    UPDATE_PATH_SUFFIX,
    WU_DOH_URLS,
    WU_HOST,
    WU_MIN_DNS_TTL,
    WU_TIMEOUT,
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
        self._rejected_ids: set[str | None] = set()
        # Recent requests that weren't uploads, for troubleshooting via diagnostics.
        self.unrecognized_requests: deque[dict[str, str]] = deque(maxlen=10)

    @property
    def available(self) -> bool:
        """Return True if the station reported recently."""
        return self.last_update is not None and dt_util.utcnow() - self.last_update < STALE_AFTER

    async def async_start(self) -> None:
        """Start the HTTP listener the station uploads to."""
        app = web.Application()
        # Catch every request: firmwares vary in path case and method, and logging
        # the ones we don't understand is the only way to troubleshoot them.
        app.router.add_route("*", "/{path:.*}", self._handle_request)
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

    async def _handle_request(self, request: web.Request) -> web.Response:
        """Handle a request. Answer uploads with `success` so the station never retries."""
        if not request.path.lower().endswith(UPDATE_PATH_SUFFIX):
            self._log_unrecognized(request)
            raise web.HTTPNotFound

        query: dict[str, str] = dict(request.query)
        if request.method == "POST":
            query.update({k: v for k, v in (await request.post()).items() if isinstance(v, str)})
        _LOGGER.debug(
            "Upload from %s (%s %s) with fields: %s",
            request.remote,
            request.method,
            request.path,
            ", ".join(sorted(k for k in query if k.lower() not in SECRET_PARAMS)),
        )
        self.async_process_upload(query)
        return web.Response(text="success\n")

    def _log_unrecognized(self, request: web.Request) -> None:
        """Log a request that isn't an upload, once per method and path."""
        entry = {
            "time": dt_util.utcnow().isoformat(),
            "remote": request.remote or "",
            "method": request.method,
            "path": request.path,
        }
        if not any(
            seen["method"] == entry["method"] and seen["path"] == entry["path"]
            for seen in self.unrecognized_requests
        ):
            _LOGGER.warning(
                "Received %s %s from %s, which isn't a weather station upload "
                "(expected %s). If this is your station, please report it",
                request.method,
                request.path,
                request.remote,
                UPDATE_PATH,
            )
        self.unrecognized_requests.append(entry)

    @callback
    def async_process_upload(self, query: Mapping[str, str]) -> None:
        """Parse an upload, update state and notify entities."""
        params = {key.lower(): value for key, value in query.items()}

        if self.station_id and (station := params.get("id")) != self.station_id:
            if station not in self._rejected_ids:
                self._rejected_ids.add(station)
                _LOGGER.warning(
                    "Ignoring uploads from station ID %s: the station ID filter only accepts %s",
                    station,
                    self.station_id,
                )
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

    The local DNS points the Weather Underground hostname back at Home
    Assistant, and many routers also intercept plain DNS sent to public
    servers. So the real address is looked up with DNS-over-HTTPS, which can't
    be intercepted, and the upload is sent to that IP with the proper Host
    header.
    """

    def __init__(
        self, session: ClientSession, station_id: str | None, station_key: str | None
    ) -> None:
        """Initialize the forwarder."""
        self._session = session
        self._station_id = station_id
        self._station_key = station_key
        self._address: str | None = None
        self._address_expires = 0.0

    async def _async_resolve(self) -> str | None:
        """Return Weather Underground's public IP address, cached for its TTL."""
        if self._address and time.monotonic() < self._address_expires:
            return self._address
        for url in WU_DOH_URLS:
            try:
                async with self._session.get(
                    url,
                    params={"name": WU_HOST, "type": "A"},
                    headers={"Accept": "application/dns-json"},
                    timeout=ClientTimeout(total=WU_TIMEOUT),
                ) as resp:
                    answer = await resp.json(content_type=None)
            except (ClientError, TimeoutError, ValueError) as err:
                _LOGGER.debug("DNS-over-HTTPS lookup via %s failed: %s", url, err)
                continue
            for record in answer.get("Answer", []):
                if record.get("type") != 1:  # A record
                    continue
                try:
                    address = ipaddress.ip_address(record["data"])
                except (KeyError, ValueError):
                    continue
                if address.is_global:
                    self._address = str(address)
                    self._address_expires = time.monotonic() + max(
                        int(record.get("TTL", 0)), WU_MIN_DNS_TTL
                    )
                    return self._address
        return None

    async def async_forward(self, query: Mapping[str, str]) -> None:
        """Send one upload to Weather Underground."""
        params = dict(query)
        if self._station_id:
            params["ID"] = self._station_id
        if self._station_key:
            params["PASSWORD"] = self._station_key

        if (address := await self._async_resolve()) is None:
            _LOGGER.warning(
                "Not forwarding to Weather Underground: could not look up a public address for %s",
                WU_HOST,
            )
            return
        try:
            async with self._session.get(
                f"http://{address}{UPDATE_PATH}",
                params=params,
                headers={"Host": WU_HOST},
                timeout=ClientTimeout(total=WU_TIMEOUT),
            ) as resp:
                body = (await resp.text()).strip()
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning("Failed to forward to Weather Underground: %s", err)
            self._address = None  # look the address up again next time
            return
        if resp.status != 200 or body.lower() != "success":
            _LOGGER.warning(
                "Weather Underground rejected the upload (HTTP %s): %s",
                resp.status,
                body[:200],
            )
