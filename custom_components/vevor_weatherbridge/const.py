"""Constants for the VEVOR Weatherbridge integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "vevor_weatherbridge"

MANUFACTURER: Final = "VEVOR"
MODEL: Final = "7-in-1 Weather Station"

# The station always uploads to this path on port 80 (Weather Underground protocol).
UPDATE_PATH: Final = "/weatherstation/updateweatherstation.php"
# Matched case-insensitively against the end of the path, as firmwares vary.
UPDATE_PATH_SUFFIX: Final = "/updateweatherstation.php"
DEFAULT_PORT: Final = 80
DEFAULT_NAME: Final = "Weather Station"

CONF_STATION_ID: Final = "station_id"
CONF_WU_FORWARD: Final = "wu_forward"
CONF_WU_STATION_ID: Final = "wu_station_id"
CONF_WU_STATION_KEY: Final = "wu_station_key"

# Forwarding target. Its address is looked up with DNS-over-HTTPS because the
# local DNS (and often anything sent to port 53) points it at Home Assistant.
WU_HOST: Final = "rtupdate.wunderground.com"
WU_DOH_URLS: Final = ["https://cloudflare-dns.com/dns-query", "https://dns.google/resolve"]
WU_MIN_DNS_TTL: Final = 300
WU_TIMEOUT: Final = 10

# Sensors become unavailable if the station stops reporting for this long.
STALE_AFTER: Final = timedelta(minutes=15)

# Query parameters that carry credentials and must never be logged or exposed.
SECRET_PARAMS: Final = {"id", "password"}
