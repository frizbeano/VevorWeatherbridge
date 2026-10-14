# VEVOR Weatherbridge

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/frizbeano/VevorWeatherbridge/actions/workflows/validate.yml/badge.svg)](https://github.com/frizbeano/VevorWeatherbridge/actions/workflows/validate.yml)
[![Tests](https://github.com/frizbeano/VevorWeatherbridge/actions/workflows/tests.yml/badge.svg)](https://github.com/frizbeano/VevorWeatherbridge/actions/workflows/tests.yml)

> This is a fork of [C9H13NO3-dev/VevorWeatherbridge](https://github.com/C9H13NO3-dev/VevorWeatherbridge), which created the original Docker/MQTT relay. This fork adds a native Home Assistant integration installable through HACS. See [Credits](#credits).

Get live data from a **VEVOR 7-in-1 Wi-Fi weather station** (model YT60234, or any station that uploads in the Weather Underground format) into Home Assistant, fully locally.

The station only knows how to upload to Weather Underground. By pointing the Weather Underground hostname at Home Assistant with a DNS override, the uploads land in Home Assistant instead, and can optionally be passed on to Weather Underground as well.

There are two ways to run it:

- **[Home Assistant integration](#home-assistant-integration-hacs)** (recommended), installed through HACS. No MQTT broker or extra container needed.
- **[Standalone Docker relay](#standalone-docker-relay-mqtt)**, which publishes to Home Assistant over MQTT.

---

## Home Assistant integration (HACS)

### Installation

1. In Home Assistant, open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/frizbeano/VevorWeatherbridge` with type **Integration**.
3. Find **VEVOR Weatherbridge** in HACS, download it, and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → VEVOR Weatherbridge**.

Requires Home Assistant 2025.2 or newer.

### Configuration

| Option | Description |
| --- | --- |
| Name | Name of the weather station device. |
| Port | Port Home Assistant listens on for uploads. Default `80`. |
| Station ID filter | Optional. Only accept uploads with this station ID. Leave empty to accept any. |

The port and station ID filter can be changed later with **Reconfigure**.

Under **Configure** (options) you can enable **Weather Underground forwarding** and optionally override the Weather Underground station ID and key. Forwarding resolves Weather Underground through public DNS (8.8.8.8 / 1.1.1.1), so it works even though your local DNS points that hostname at Home Assistant.

> **About port 80.** The station always uploads to port 80, so the integration opens its own listener there (separate from the Home Assistant UI on 8123). If something else on the Home Assistant host already uses port 80, such as the NGINX add-on, either free that port or have that service forward `/weatherstation/updateweatherstation.php` to the port you configure here.

### Sensors

A sensor is created the first time the station reports that value, so you only get sensors your station actually sends.

| Sensor | Station field |
| --- | --- |
| Temperature, Indoor temperature, Dew point, Wind chill, Heat index | `tempf`, `indoortempf`, `dewptf`, `windchillf`, `heatindexf` |
| Humidity, Indoor humidity | `humidity`, `indoorhumidity` |
| Relative pressure, Absolute pressure | `baromin`, `absbaromin` |
| Wind speed, Wind gust, Wind direction | `windspeedmph`, `windgustmph`, `winddir` |
| Rain rate | `rainin` |
| Daily / Weekly / Monthly / Yearly rain | `dailyrainin`, `weeklyrainin`, `monthlyrainin`, `yearlyrainin` |
| Solar radiation, UV index | `solarradiation`, `UV` |
| Last update (diagnostic) | `dateutc` |

**Units follow your Home Assistant unit system automatically**: metric installations get °C, hPa, km/h and mm, and imperial installations get °F, inHg, mph and in. Any sensor's unit can be changed in its entity settings. All measurement sensors record long-term statistics.

Sensors become unavailable if the station hasn't reported for 15 minutes.

---

## Station and DNS setup

This step is needed for both installation methods.

1. Redirect `rtupdate.wunderground.com` to the IP of your Home Assistant host (or the Docker host). The easiest way is a local DNS record in Pi-hole, AdGuard Home, or your router:

   ```
   rtupdate.wunderground.com    <your-home-assistant-ip>
   ```

   If your router has **DNS rebind protection**, allow this domain, or the override will be blocked.

2. In the station's app or setup page, enable **Weather Underground** uploads. Any station ID and key works, unless you also want to forward to a real Weather Underground account.

The station then sends requests like:

```
GET /weatherstation/updateweatherstation.php?ID=...&PASSWORD=...&dateutc=2026-10-14+12:00:00&tempf=68.0&humidity=55&baromin=29.92&...
```

---

## Standalone Docker relay (MQTT)

Use this if Home Assistant runs somewhere that can't listen on port 80, or if you prefer MQTT. It needs an MQTT broker, and the [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) set up in Home Assistant.

1. Clone the repository:

   ```bash
   git clone https://github.com/frizbeano/VevorWeatherbridge.git
   cd VevorWeatherbridge
   ```

2. Edit the environment in `docker-compose.yml`:

   | Variable | Default | Description |
   | --- | --- | --- |
   | `MQTT_HOST` / `MQTT_PORT` | `localhost` / `1883` | MQTT broker. |
   | `MQTT_USER` / `MQTT_PASSWORD` | – | Broker credentials, if required. |
   | `MQTT_PREFIX` | `homeassistant` | MQTT discovery prefix. |
   | `DEVICE_ID` | `weather_station` | Unique ID for the device. Changing it creates new entities. |
   | `DEVICE_NAME` | `Weather Station` | Device name in Home Assistant. |
   | `DEVICE_MANUFACTURER` / `DEVICE_MODEL` | `VEVOR` / `7-in-1 Weather Station` | Device info. |
   | `UNITS` | `metric` | `metric` or `imperial`. |
   | `TZ` | `UTC` | Time zone for the `measured_on` attribute. |
   | `PORT` | `80` | Port to listen on inside the container. |
   | `WU_FORWARD` | `false` | Also forward uploads to Weather Underground. |
   | `WU_USERNAME` / `WU_PASSWORD` | – | Override the station ID and key when forwarding. |
   | `LOG_LEVEL` | `INFO` | Logging verbosity. |

3. Start it:

   ```bash
   docker compose up --build -d
   docker compose logs -f
   ```

Sensors are grouped under one device and go unavailable when the relay is stopped.

---

## Troubleshooting

- **No sensors appear.** Check that the station's DNS lookup returns your Home Assistant IP (`nslookup rtupdate.wunderground.com <your-dns-server>`), and that port 80 on that host is reachable from the station's network.
- **Integration fails to set up with "Cannot listen on port 80".** Another service is using port 80. See [About port 80](#configuration).
- **Debug logging** for the integration:

  ```yaml
  logger:
    logs:
      custom_components.vevor_weatherbridge: debug
  ```

- **Diagnostics.** Download them from the integration's device page. They include the last upload, with the station ID and key removed.

---

## Development

```bash
pip install -r requirements_test.txt
pytest
ruff check . && ruff format --check .
```

### Releasing

1. Bump `version` in `custom_components/vevor_weatherbridge/manifest.json` and add an entry to [CHANGELOG.md](CHANGELOG.md).
2. Commit, then create a GitHub release tagged with the same version (for example `v1.1.0`). HACS offers the new release as an update.

---

## License

[MIT](LICENSE). The original project by @C9H13NO3-dev was released under [CC0 1.0](https://github.com/C9H13NO3-dev/VevorWeatherbridge/blob/main/LICENSE) (public domain dedication), which allows this fork to be relicensed.

## Credits

- **[@C9H13NO3-dev](https://github.com/C9H13NO3-dev)** wrote the original [VevorWeatherbridge](https://github.com/C9H13NO3-dev/VevorWeatherbridge): the Python relay, Docker setup, MQTT discovery, and Weather Underground forwarding this project builds on.
- **[@vlovmx](https://github.com/vlovmx)** wrote the Weather Underground relay script that inspired the original.
- **[@frizbeano](https://github.com/frizbeano)** maintains this fork and the Home Assistant integration.
