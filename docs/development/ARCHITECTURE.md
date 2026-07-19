# Architecture

## Test coverage ratchet

The initial extraction has a 40% enforced line-coverage floor (the measured baseline
is 44%). New behavior should include tests and must not reduce that floor. Increase
the CI threshold as coverage grows; do not preserve the number with exclusions or
coverage-only tests.

Nutri Points owns the HTTP/SSE protocol and server-side points logic. This repository owns Home Assistant configuration, entities, actions, availability, streaming, and Repairs behavior.

## Runtime flow

Entities read normalized coordinator data and never call the API directly. The coordinator obtains day, readiness, weight, and drink data through the API client. The SSE listener requests coordinator refreshes for documented trigger events and leaves periodic polling active as the fallback.

Contract-generation differences are normalized in the API package. Version checks must not be scattered through entities or action handlers.

## Contract dependency

The server repository publishes `nutripoints-api-contracts` as an immutable GitHub Release wheel. It contains the stable OpenAPI snapshot and Home Assistant profile/fixtures for each supported generation.

The wheel is a development and test dependency only. It must not be added to `manifest.json`, imported by runtime integration code, or used to share server implementation logic.

`contract-version.txt` pins the tested artifact. The private server repository builds the wheel; this public repository distributes it under `api-contract-v*` releases so forks and public CI can fetch it. Renovate proposes updates, and CI verifies the release checksum before installation. An update is merged only after the full generation matrix passes.

## Compatibility rules

- Preserve config-entry keys, entity unique ids, action names/fields, and state semantics within the pre-1.0 release line unless a migration is provided.
- Test every generation listed in `SUPPORTED_API_CONTRACT_TAGS`.
- Additive server behavior may expand the newest package generation without removing older fixtures.
- Breaking server behavior requires a new `stable-rw-vN` generation and an explicit integration release.
- Network calls are mocked in tests; no test depends on a live Nutri Points instance.

## Package responsibilities

- `api/`: authenticated HTTP, SSE parsing, error mapping, generation normalization.
- `coordinator/`: refresh orchestration, independent dataset availability, stream lifecycle.
- `config_flow.py`: setup and reconfiguration validation.
- `sensor/` and `binary_sensor/`: Home Assistant entity presentation only.
- `service_actions/`: action schemas, templated input parsing, and write dispatch.
- `repairs.py`: persistent runtime issue classification and cleanup.
