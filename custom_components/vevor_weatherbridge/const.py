"""Constants for the VEVOR Weatherbridge integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "vevor_weatherbridge"

MANUFACTURER: Final = "VEVOR"
MODEL: Final = "7-in-1 Weather Station"

# The station always uploads to this path on port 80 (Weather Underground protocol).
UPDATE_PATH: Final = "/weatherstation/updateweatherstation.php"
DEFAULT_PORT: Final = 80
DEFAULT_NAME: Final = "Weather Station"

CONF_STATION_ID: Final = "station_id"
CONF_WU_FORWARD: Final = "wu_forward"
CONF_WU_STATION_ID: Final = "wu_station_id"
CONF_WU_STATION_KEY: Final = "wu_station_key"

# Forwarding target. Resolved through public DNS because the local DNS is
# normally overridden to point this hostname at Home Assistant itself.
WU_HOST: Final = "rtupdate.wunderground.com"
WU_URL: Final = f"http://{WU_HOST}{UPDATE_PATH}"
WU_NAMESERVERS: Final = ["8.8.8.8", "1.1.1.1"]
WU_TIMEOUT: Final = 10

# Sensors become unavailable if the station stops reporting for this long.
STALE_AFTER: Final = timedelta(minutes=15)

# Query parameters that carry credentials and must never be logged or exposed.
SECRET_PARAMS: Final = {"id", "password"}
