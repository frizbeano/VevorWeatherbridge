# Changelog

## 1.0.2

### Added
- Requests that aren't weather station uploads are now logged, once per path, and listed in diagnostics. Previously they were silently ignored, which made a misconfigured station impossible to troubleshoot.
- Debug logging now shows each upload's source and field names.

### Changed
- Uploads sent with POST, or to the upload path in different letter case, are now accepted.

## 1.0.1

### Added
- Integration icon, shown in Home Assistant 2026.3 and newer.
- A warning is logged when the station ID filter rejects uploads.

### Fixed
- Weather Underground forwarding looped back to the local network on routers that intercept DNS sent to public servers. The address is now looked up with DNS-over-HTTPS, and private addresses are never used. This applies to both the integration and the Docker relay; the relay no longer needs `dnspython`.

## 1.0.0

First release of this fork of [C9H13NO3-dev/VevorWeatherbridge](https://github.com/C9H13NO3-dev/VevorWeatherbridge).

### Added
- Home Assistant integration, installable through HACS. It receives station uploads directly, so no MQTT broker is needed.
- Setup from the UI, reconfiguring of the port and station ID filter, and Weather Underground forwarding in the options.
- Sensors for indoor temperature and humidity, wind chill, heat index, absolute pressure, weekly/monthly/yearly rain, and the time of the last update.
- Long-term statistics for all measurement sensors.
- Diagnostics download, with credentials removed.
- Tests, plus CI for hassfest, HACS validation, ruff and pytest.

### Changed
- License changed from CC0 1.0 to MIT, so the repository passes HACS validation.

### Fixed (Docker/MQTT relay)
- Crash at startup with paho-mqtt 2.x. Dependencies are now pinned.
- A malformed value returned an HTTP 500 error and made the station retry.
- Solar radiation was never published (`solarRadiation` vs `solarradiation`).
- `rainin` was published as a rain total. It is now a rain rate.
- Entity names repeated the device name.
- Startup crashed if the MQTT broker wasn't reachable yet.
- The Flask development server is replaced with waitress.
