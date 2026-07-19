# Getting started

## Requirements

- Home Assistant 2026.4 or newer
- A reachable Nutri Points server
- A Nutri Points API key
- HACS for the recommended installation path

## Install

1. In HACS, add `https://github.com/megageek/nutripoints-homeassistant` as a custom Integration repository.
2. Install **Nutri Points** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and select **Nutri Points**.
4. Enter the server base URL and API key. The flow validates the server and its API contract before saving.

If upgrading from the formerly bundled component, remove or rename
`custom_components/nutri_points`, restart, install this HACS repository, restart again,
and reload the existing config entry. The entry data and entity unique IDs are retained.

See [Configuration](./CONFIGURATION.md) for every option and [Examples](./EXAMPLES.md)
for dashboards and automations.

## Troubleshooting

Enable diagnostic logging while reproducing a problem:

```yaml
logger:
  logs:
    custom_components.nutri_points: debug
```

Contract errors mean the server exposes a generation the installed integration does
not support. Upgrade the integration or server; do not bypass the compatibility check.
