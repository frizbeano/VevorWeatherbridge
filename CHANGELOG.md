# Changelog

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
