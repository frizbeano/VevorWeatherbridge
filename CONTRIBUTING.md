# Contributing

Thanks for helping out! Bug reports, new station models and fixes are all welcome.

## Reporting a problem

Please use the [bug report form](https://github.com/frizbeano/VevorWeatherbridge/issues/new/choose) and attach diagnostics. Most "no sensors" problems are covered in the [troubleshooting guide](README.md#troubleshooting).

**A station that sends a different format:** look in the Home Assistant log for `Received … which isn't a weather station upload`, or under `unrecognized_requests` in diagnostics, and include it in the issue. That's usually all that's needed to add support.

## Development setup

The repository contains two independent parts:

| Part | Code | Tests | Python |
| --- | --- | --- | --- |
| Home Assistant integration | `custom_components/vevor_weatherbridge/` | `tests/` | 3.13 |
| Docker/MQTT relay | `weatherstation.py` | `relay_tests/` | 3.12 |

```bash
# Integration
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pytest --cov=custom_components.vevor_weatherbridge

# Relay (separate virtualenv, since the integration test harness pins its own packages)
python3.12 -m venv .venv-relay && source .venv-relay/bin/activate
pip install -r requirements_relay_test.txt
pytest relay_tests

# Lint and format checks run automatically on commit
pip install pre-commit && pre-commit install
```

To try the integration in a real Home Assistant, copy `custom_components/vevor_weatherbridge` into your Home Assistant `config/custom_components/` and restart. To send a test upload without a station, use the `curl` command from the [troubleshooting guide](README.md#narrow-down-where-the-problem-is).

## Pull requests

- Keep each pull request focused on one change, and add or update tests.
- CI must pass: ruff, integration tests (at least 90% coverage), relay tests, Docker build, hassfest and HACS validation.
- Add a line to `CHANGELOG.md` under `## Unreleased` for anything users would notice.
- New sensors: add the Weather Underground field to `SENSORS` in `sensor.py`, its name to `translations/en.json`, and a row to the README table.

## Icon

The integration icon is in `custom_components/vevor_weatherbridge/brand/`. Home Assistant 2026.3 and newer load it from there. To change it, edit `assets/icon.svg` and export it as a trimmed, transparent square PNG at 256×256 (`icon.png`) and 512×512 (`icon@2x.png`).

## Releasing (maintainers)

1. Rename `## Unreleased` in `CHANGELOG.md` to the new version, for example `## 1.1.0`, and set the same `version` in `custom_components/vevor_weatherbridge/manifest.json`.
2. Merge that to `main`.
3. Tag the merge commit and push the tag:

   ```bash
   git tag v1.1.0 && git push origin v1.1.0
   ```

The release workflow checks that the tag matches the manifest version, then publishes a GitHub release with that version's changelog section as notes. HACS offers it to users as an update.

Versions follow [semantic versioning](https://semver.org/): patch for fixes, minor for new features or sensors, and major for changes that need users to do something.
