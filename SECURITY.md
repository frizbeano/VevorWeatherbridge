# Security policy

## Reporting a vulnerability

Please **don't** open a public issue. Report it privately through [GitHub's private vulnerability reporting](https://github.com/frizbeano/VevorWeatherbridge/security/advisories/new). You'll get a reply within a week.

## Supported versions

Only the latest release gets security fixes.

## Security model

The weather station's upload protocol has no real authentication. Its station ID and key are sent in plain HTTP. So both the integration and the Docker relay accept uploads from **anyone who can reach their port**, which is port 80 by default.

- Don't expose the listening port to the internet. It's meant for your local network only.
- In the integration, set the **station IP address** so only your station can send data. Forwarding to Weather Underground only runs when it's set. Addresses can be spoofed on the local network, so this keeps out other devices, not a determined attacker on your LAN.
- Set a **station ID filter** so uploads from other IDs are rejected. Anyone on your network who knows the ID can still send data, though.
- The integration forwards to Weather Underground over HTTPS with certificate verification. The Docker relay still forwards over plain HTTP, like the station itself.
- Weather Underground credentials, if you set them for forwarding, are stored in Home Assistant's config entry. They're removed from diagnostics and never logged.

Reports in scope include ways to crash or hang Home Assistant through the listener, to leak credentials, or to make forwarding send data somewhere unintended.
