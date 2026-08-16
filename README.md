# Nutri Points for Home Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.4%2B-blue.svg)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

The official custom integration for a self-hosted [Nutri Points](https://github.com/megageek/nutripoints) server. It exposes nutrition, activity, drinks, weight, and readiness state to Home Assistant and provides replay-safe write actions for automations.

## Installation

1. In HACS, add `https://github.com/megageek/nutripoints-homeassistant` as a custom **Integration** repository.
2. Install **Nutri Points** and restart Home Assistant.
3. In Nutri Points, create an API key under **Settings → API Keys**.
4. Add the integration under **Settings → Devices & services** with the server URL and API key.

Home Assistant 2026.4 or newer is required.

When migrating from the component previously bundled in the Nutri Points server repository, remove only the old HACS repository/package before installing this one. Do not delete the existing Home Assistant config entry: the domain, stored settings, entity unique ids, and action names remain compatible.

## Behavior

- Polls the current day, readiness, weight overview, and drink totals.
- Uses the authenticated Nutri Points SSE stream for immediate refresh triggers.
- Provides filterable automation triggers for food logs, weigh-in summaries, recipe-batch label requests, and
  food-weighing session starts.
- Persists the last durable event ID per config entry and replays missed events after reconnect. If server retention has elapsed, a Repair identifies the gap before the integration resumes.
- Falls back to polling automatically while the stream is disconnected.
- Exposes point, drink, weight, planning, budget, and weigh-in entities.
- Reports persistent authentication, host, network-policy, contract, and transport failures through Repairs.
- Registers nutrition logging and food-weighing projection, preview, completion, and cancellation actions under
  the `nutri_points` domain.
- Creates one Nutri Points device with translated entities and downloadable, credential-redacted diagnostics.

The integration supports Nutri Points contract generations `stable-rw-v1` through `stable-rw-v10`. Unknown
generations are rejected during setup so incompatible data cannot silently reach automations. Food-weighing
sessions require `stable-rw-v7` and the `ha_food_weighing_sessions_v1` capability; older servers continue to
provide their existing entities and actions.

One Nutri Points server can be configured per Home Assistant installation. Connection settings can be changed with **Reconfigure**, while polling and threshold settings remain under **Options**. Home Assistant starts **Reconfigure authentication** automatically if the API key expires.

## Development

Open the repository in its Dev Container, then use the provided scripts:

```bash
./script/setup/bootstrap
./script/test --cov
./script/check
./script/hassfest
```

Tests use `pytest-homeassistant-custom-component` and the versioned `nutripoints-api-contracts` wheel built by the server repository and distributed from the public [contract repository](https://github.com/megageek/nutripoints-api-contracts). Contract updates are proposed by Renovate and always require review.

See [architecture](docs/development/ARCHITECTURE.md), [configuration](docs/user/CONFIGURATION.md), and [release process](docs/development/RELEASE.md) for details.

## License

MIT
