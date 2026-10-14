<img src="custom_components/vevor_weatherbridge/brand/icon.png" alt="" width="96" align="right">

# VEVOR Weatherbridge

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=frizbeano&repository=VevorWeatherbridge&category=integration)
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

**Quick install.** These buttons open your own Home Assistant instance:

1. Open the repository in HACS, then download it and restart Home Assistant:

   [![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=frizbeano&repository=VevorWeatherbridge&category=integration)

2. Add the integration:

   [![Open your Home Assistant instance and start setting up VEVOR Weatherbridge.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=vevor_weatherbridge)

**Manual install:**

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

Under **Configure** (options) you can enable **Weather Underground forwarding** and optionally override the Weather Underground station ID and key. Forwarding looks up Weather Underground's real address with DNS-over-HTTPS (Cloudflare, then Google). That way it works even though your local DNS points that hostname at Home Assistant, and even if your router intercepts ordinary DNS queries.

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

2. Turn on Weather Underground uploads on the station. **Connecting the station to Wi-Fi is not enough.** It sends nothing until this is set.
   1. Put the console into Wi-Fi setup mode, the same way you first connected it. This is usually a long press on the Wi-Fi or SET button; see the station's manual.
   2. Connect to the station's own hotspot and open its setup page. This is usually `http://192.168.4.1`.
   3. Tick **Upload to wunderground.com**.
   4. Enter any **Station ID** and **Key**, for example `HOME1` and `abc123`. If you set a station ID filter in the integration, the ID must match it.
   5. Save or apply, and let the station rejoin your Wi-Fi.

   If you also want your data on Weather Underground, enter a real Weather Underground station ID and key instead, and turn on forwarding in the integration's options.

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

### No sensors, only "Last update"

The measurement sensors are only created when the first upload arrives, so this means no upload has been accepted yet. Go through these checks in order. The first two account for most cases.

1. **Upload is not enabled on the station.** Joining the station to Wi-Fi does not turn on uploads. In the station's setup page, tick **Upload to wunderground.com** and fill in a station ID and key. See [Station and DNS setup](#station-and-dns-setup).

2. **The DNS override points at the wrong IP.** Run `nslookup rtupdate.wunderground.com`. It must return your **Home Assistant** IP. Two mistakes are common: entering the *station's* own IP, and leaving an old entry from a previous relay host.

3. **The station is still using the old address.** Power-cycle the station after changing DNS.

4. **The station ID filter doesn't match.** If you set one, look in the Home Assistant log for `Ignoring uploads from station ID …`. Either match the ID on the station or clear the filter with **Reconfigure**.

5. **The station uses a format the integration doesn't recognize.** Look in the log for `Received … which isn't a weather station upload`. The station *is* reaching Home Assistant, but its request isn't recognized. Please [open an issue](https://github.com/frizbeano/VevorWeatherbridge/issues) with that log line. The same requests are listed under `unrecognized_requests` in diagnostics.

6. **DNS rebind protection** on your router or Pi-hole is blocking the override, because it resolves a public hostname to a private IP. Add `rtupdate.wunderground.com` to the allowed domains.

### Narrow down where the problem is

Check each link in the chain from another computer on the same network:

```bash
# 1. DNS: must print your Home Assistant IP
nslookup rtupdate.wunderground.com

# 2. Listener: must print "404: Not Found" (that's the integration answering), not time out
curl http://<home-assistant-ip>/

# 3. Full path: send one test upload exactly as the station would. Must print "success".
#    Use your station ID filter's value for ID, if you set one.
curl "http://rtupdate.wunderground.com/weatherstation/updateweatherstation.php?ID=HOME1&PASSWORD=test&dateutc=now&tempf=59&humidity=70"
```

If step 3 creates Temperature and Humidity sensors, the integration and DNS work, and the problem is on the station (check 1 above). The test values are replaced by the station's next real upload.

The log messages map to the problem like this:

| Log message | Meaning |
| --- | --- |
| *(nothing at all)* | Nothing is reaching Home Assistant: check upload is enabled, then DNS. |
| `Ignoring uploads from station ID X` | Station ID filter mismatch. |
| `Received GET /… which isn't a weather station upload` | Unrecognized format. Please open an issue. |
| `Upload from … with fields: …` (debug) | Uploads are arriving normally. |

### Other problems

- **"Last update" has a value, but some sensors are missing.** The station doesn't send those values. Download diagnostics to see exactly what it sends.
- **Sensors go unavailable after a while.** The station stopped uploading for 15 minutes. Check its Wi-Fi signal and power.
- **Integration fails to set up with "Cannot listen on port 80".** Another service on the Home Assistant host is using port 80. See [About port 80](#configuration).
- **Weather Underground forwarding fails.** The log says why. "Rejected (HTTP 401)" means the Weather Underground station ID or key is wrong.

### Debug logging and diagnostics

Turn on debug logging to see every upload as it arrives. Either use **Enable debug logging** on the integration's page, or add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.vevor_weatherbridge: debug
```

**Diagnostics** can be downloaded from the device page. They include the last upload and any unrecognized requests, with the station ID and key removed. Attach them when opening an issue.

---

## Contributing

Bug reports and pull requests are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) covers the development setup, tests and the release process. To report a security problem, see [SECURITY.md](SECURITY.md).

---

## License

[MIT](LICENSE). The original project by @C9H13NO3-dev was released under [CC0 1.0](https://github.com/C9H13NO3-dev/VevorWeatherbridge/blob/main/LICENSE) (public domain dedication), which allows this fork to be relicensed.

## Credits

- **[@C9H13NO3-dev](https://github.com/C9H13NO3-dev)** wrote the original [VevorWeatherbridge](https://github.com/C9H13NO3-dev/VevorWeatherbridge): the Python relay, Docker setup, MQTT discovery, and Weather Underground forwarding this project builds on.
- **[@vlovmx](https://github.com/vlovmx)** wrote the Weather Underground relay script that inspired the original.
- **[@frizbeano](https://github.com/frizbeano)** maintains this fork and the Home Assistant integration.
