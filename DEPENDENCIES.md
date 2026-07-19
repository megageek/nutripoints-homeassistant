# Dependencies

The integration has no third-party runtime dependency. It uses Home Assistant's
`aiohttp` client and APIs, and `manifest.json` therefore keeps `requirements` empty.

Development dependencies are installed by `script/setup/bootstrap`:

- Home Assistant 2026.4 and its test tooling
- `pytest-homeassistant-custom-component`
- Ruff, Pyright, pre-commit, codespell, and Markdown tooling
- `nutripoints-api-contracts`, built by Nutri Points and downloaded from the pinned,
  immutable public integration release in `contract-version.txt`

The bootstrap hook verifies the wheel against the release's SHA-256 manifest before installation.
For local cross-repository development, set `NUTRIPOINTS_CONTRACT_WHEEL` to a wheel
built from the Nutri Points repository. Runtime code does not import this package;
it supplies versioned fixtures and schemas to the test suite.
