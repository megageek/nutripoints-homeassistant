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
- Falls back to polling automatically while the stream is disconnected.
- Exposes point, drink, weight, planning, budget, and weigh-in entities.
- Reports persistent authentication, host, network-policy, contract, and transport failures through Repairs.
- Registers `log_food`, `log_activity`, `log_drink`, `log_weight`, and `set_steps` actions under the `nutri_points` domain.

The integration supports Nutri Points contract generations `stable-rw-v1`, `stable-rw-v2`, and `stable-rw-v3`. Unknown generations are rejected during setup so incompatible data cannot silently reach automations.

## Development

Open the repository in its Dev Container, then use the provided scripts:

```bash
./script/setup/bootstrap
./script/test --cov
./script/check
./script/hassfest
```

Tests use `pytest-homeassistant-custom-component` and the versioned `nutripoints-api-contracts` wheel built by the server repository and distributed as an immutable release asset from this public repository. Contract updates are proposed by Renovate and always require review.

See [architecture](docs/development/ARCHITECTURE.md), [configuration](docs/user/CONFIGURATION.md), and [release process](docs/development/RELEASE.md) for details.

## License

MIT
