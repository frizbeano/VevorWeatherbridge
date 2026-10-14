"""Standalone relay: VEVOR weather station uploads -> Home Assistant via MQTT discovery.

Use this when you'd rather not run the Home Assistant integration in
custom_components/ (for example, Home Assistant runs elsewhere and you already
have an MQTT broker).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import ipaddress
import json
import logging
import math
import os
from zoneinfo import ZoneInfo

from flask import Flask, request
import paho.mqtt.client as mqtt
import requests
from waitress import serve

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
_LOGGER = logging.getLogger("weatherstation")

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
MQTT_PREFIX = os.environ.get("MQTT_PREFIX", "homeassistant")
DEVICE_ID = os.environ.get("DEVICE_ID", "weather_station")
DEVICE_NAME = os.environ.get("DEVICE_NAME", "Weather Station")
DEVICE_MANUFACTURER = os.environ.get("DEVICE_MANUFACTURER", "VEVOR")
DEVICE_MODEL = os.environ.get("DEVICE_MODEL", "7-in-1 Weather Station")
TIMEZONE = os.environ.get("TZ", "UTC")
METRIC = os.environ.get("UNITS", "metric").lower() != "imperial"
PORT = int(os.environ.get("PORT", 80))
WU_FORWARD = os.environ.get("WU_FORWARD", "false").lower() == "true"
WU_USERNAME = os.environ.get("WU_USERNAME")
WU_PASSWORD = os.environ.get("WU_PASSWORD")

WU_HOST = "rtupdate.wunderground.com"
WU_DOH_URLS = ["https://cloudflare-dns.com/dns-query", "https://dns.google/resolve"]
UPDATE_PATH = "/weatherstation/updateweatherstation.php"
AVAILABILITY_TOPIC = f"vevor_weatherbridge/{DEVICE_ID}/availability"


@dataclass(frozen=True)
class Sensor:
    """A Weather Underground parameter published as a Home Assistant sensor."""

    param: str  # lowercase WU query parameter
    object_id: str  # kept stable: forms the MQTT unique_id
    name: str
    device_class: str | None
    imperial_unit: str
    metric_unit: str
    to_metric: Callable[[float], float] = lambda v: v
    precision: int = 1
    state_class: str = "measurement"


def _f_to_c(f: float) -> float:
    return (f - 32) * 5 / 9


def _temperature(param: str, object_id: str, name: str) -> Sensor:
    return Sensor(param, object_id, name, "temperature", "°F", "°C", _f_to_c)


def _rain_total(param: str, object_id: str, name: str) -> Sensor:
    return Sensor(
        param,
        object_id,
        name,
        "precipitation",
        "in",
        "mm",
        lambda v: v * 25.4,
        2,
        "total_increasing",
    )


def _pressure(param: str, object_id: str, name: str) -> Sensor:
    return Sensor(
        param, object_id, name, "atmospheric_pressure", "inHg", "hPa", lambda v: v * 33.8639
    )


def _wind(param: str, object_id: str, name: str) -> Sensor:
    return Sensor(param, object_id, name, "wind_speed", "mph", "km/h", lambda v: v * 1.609344)


SENSORS = [
    _temperature("tempf", "temperature", "Temperature"),
    _temperature("indoortempf", "indoor_temperature", "Indoor temperature"),
    _temperature("dewptf", "dew_point", "Dew point"),
    _temperature("windchillf", "wind_chill", "Wind chill"),
    Sensor("humidity", "humidity", "Humidity", "humidity", "%", "%", precision=0),
    Sensor(
        "indoorhumidity", "indoor_humidity", "Indoor humidity", "humidity", "%", "%", precision=0
    ),
    _pressure("baromin", "barometric_pressure", "Relative pressure"),
    _pressure("absbaromin", "absolute_pressure", "Absolute pressure"),
    _wind("windspeedmph", "wind_speed", "Wind speed"),
    _wind("windgustmph", "wind_gust_speed", "Wind gust"),
    Sensor(
        "winddir",
        "wind_direction",
        "Wind direction",
        "wind_direction",
        "°",
        "°",
        precision=0,
        state_class="measurement_angle",
    ),
    # `rainin` is the rain over the past hour, i.e. a rate.
    Sensor(
        "rainin",
        "rainfall",
        "Rain rate",
        "precipitation_intensity",
        "in/h",
        "mm/h",
        lambda v: v * 25.4,
        2,
    ),
    _rain_total("dailyrainin", "daily_rainfall", "Daily rain"),
    _rain_total("weeklyrainin", "weekly_rainfall", "Weekly rain"),
    _rain_total("monthlyrainin", "monthly_rainfall", "Monthly rain"),
    _rain_total("yearlyrainin", "yearly_rainfall", "Yearly rain"),
    Sensor("solarradiation", "solar_radiation", "Solar radiation", "irradiance", "W/m²", "W/m²"),
    Sensor("uv", "uv_index", "UV index", None, "UV index", "UV index", precision=0),
]


def parse_value(raw: str | None) -> float | None:
    """Convert a raw value to float; None if missing, invalid or WU's -9999 sentinel."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value) or value <= -9999:
        return None
    return value


def local_time(dateutc: str | None) -> str:
    """Convert the station's UTC timestamp to local time."""
    try:
        parsed = datetime.strptime(dateutc or "", "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        parsed = datetime.now(UTC)
    return parsed.astimezone(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")


class Publisher:
    """Publish sensors via MQTT discovery, reconnecting automatically."""

    def __init__(self) -> None:
        self._announced: set[str] = set()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if MQTT_USER:
            self._client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        self._client.will_set(AVAILABILITY_TOPIC, "offline", retain=True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        # connect_async + loop_start retries in the background instead of
        # crashing at startup if the broker isn't up yet.
        self._client.connect_async(MQTT_HOST, MQTT_PORT, 60)
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            _LOGGER.error("MQTT connection failed: %s", reason_code)
            return
        _LOGGER.info("Connected to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
        self._announced.clear()  # re-announce in case the broker lost retained configs
        client.publish(AVAILABILITY_TOPIC, "online", retain=True)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        _LOGGER.warning("Disconnected from MQTT broker: %s", reason_code)

    def publish(self, sensor: Sensor, value: float, measured_on: str) -> None:
        base = f"{MQTT_PREFIX}/sensor/{DEVICE_ID}_{sensor.object_id}"
        if sensor.object_id not in self._announced:
            config = {
                "name": sensor.name,
                "unique_id": f"{DEVICE_ID}_{sensor.object_id}",
                "state_topic": f"{base}/state",
                "json_attributes_topic": f"{base}/attributes",
                "availability_topic": AVAILABILITY_TOPIC,
                "unit_of_measurement": sensor.metric_unit if METRIC else sensor.imperial_unit,
                "state_class": sensor.state_class,
                "suggested_display_precision": sensor.precision,
                "device": {
                    "identifiers": [DEVICE_ID],
                    "name": DEVICE_NAME,
                    "manufacturer": DEVICE_MANUFACTURER,
                    "model": DEVICE_MODEL,
                },
            }
            if sensor.device_class:
                config["device_class"] = sensor.device_class
            self._client.publish(f"{base}/config", json.dumps(config), retain=True)
            self._announced.add(sensor.object_id)

        if METRIC:
            value = sensor.to_metric(value)
        self._client.publish(f"{base}/state", str(round(value, sensor.precision)), retain=True)
        self._client.publish(
            f"{base}/attributes", json.dumps({"measured_on": measured_on}), retain=True
        )


def resolve_wunderground() -> str | None:
    """Look up WU's public address with DNS-over-HTTPS.

    Plain DNS can't be trusted here: the local DNS points the hostname at this
    relay, and many routers intercept DNS sent to public servers too.
    """
    for url in WU_DOH_URLS:
        try:
            resp = requests.get(
                url,
                params={"name": WU_HOST, "type": "A"},
                headers={"Accept": "application/dns-json"},
                timeout=10,
            )
            answers = resp.json().get("Answer", [])
        except (requests.RequestException, ValueError) as err:
            _LOGGER.debug("DNS-over-HTTPS lookup via %s failed: %s", url, err)
            continue
        for record in answers:
            if record.get("type") != 1:
                continue
            try:
                address = ipaddress.ip_address(record["data"])
            except (KeyError, ValueError):
                continue
            if address.is_global:
                return str(address)
    return None


def forward_to_wunderground(query: dict[str, str]) -> None:
    """Forward the upload to Weather Underground's real address."""
    params = dict(query)
    if WU_USERNAME:
        params["ID"] = WU_USERNAME
    if WU_PASSWORD:
        params["PASSWORD"] = WU_PASSWORD
    if (address := resolve_wunderground()) is None:
        _LOGGER.warning("Not forwarding: could not look up a public address for %s", WU_HOST)
        return
    try:
        resp = requests.get(
            f"http://{address}{UPDATE_PATH}", params=params, headers={"Host": WU_HOST}, timeout=10
        )
    except requests.RequestException as err:
        _LOGGER.warning("Failed to forward to Weather Underground: %s", err)
        return
    if resp.status_code != 200 or resp.text.strip().lower() != "success":
        _LOGGER.warning(
            "Weather Underground rejected the upload (HTTP %s): %s",
            resp.status_code,
            resp.text[:200],
        )


app = Flask(__name__)
publisher: Publisher | None = None


@app.route(UPDATE_PATH)
def update():
    query = request.args.to_dict(flat=True)
    params = {key.lower(): value for key, value in query.items()}
    measured_on = local_time(params.get("dateutc"))

    for sensor in SENSORS:
        value = parse_value(params.get(sensor.param))
        if value is not None:
            publisher.publish(sensor, value, measured_on)

    if WU_FORWARD:
        forward_to_wunderground(query)

    # Always acknowledge so the station doesn't retry.
    return "success\n", 200


if __name__ == "__main__":
    publisher = Publisher()
    _LOGGER.info("Listening on port %s", PORT)
    serve(app, host="0.0.0.0", port=PORT)
