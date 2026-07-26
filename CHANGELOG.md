# Changelog

## [0.3.0](https://github.com/megageek/nutripoints-homeassistant/compare/v0.2.0...v0.3.0) (2026-07-26)


### ⚠ BREAKING CHANGES

* default Nutri Points entity IDs are renamed with the server label during migration; manually customized entity IDs are preserved.

### Features

* **entity:** add device metadata and diagnostics ([140ff27](https://github.com/megageek/nutripoints-homeassistant/commit/140ff277eb0a938a0fbf8ba813f564e6f612ddd4))
* support persistent multi-server identity ([3fbc5f2](https://github.com/megageek/nutripoints-homeassistant/commit/3fbc5f237e31696ef73873646471510885d423fb))


### Bug Fixes

* **config:** harden entry lifecycle and reauthentication ([ae0065c](https://github.com/megageek/nutripoints-homeassistant/commit/ae0065c6690c7b5547693e0b3de58564a0e12a02))
* **tests:** restore reliable validation tooling ([7731a94](https://github.com/megageek/nutripoints-homeassistant/commit/7731a9434371cf646525e5f31f9fee70570bdac6))
