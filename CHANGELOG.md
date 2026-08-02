# Changelog

## [0.3.5](https://github.com/megageek/nutripoints-homeassistant/compare/v0.3.4...v0.3.5) (2026-08-02)


### Features

* support recipe print request events and stable-rw-v9 ([71e7dec](https://github.com/megageek/nutripoints-homeassistant/commit/71e7deccba099cf3465a83711abe76be2ae48a43))
* **trigger:** support recipe print request events ([b6f97ea](https://github.com/megageek/nutripoints-homeassistant/commit/b6f97ea309eb9e1fb5b68eec77bba6229c452a52)), closes [#18](https://github.com/megageek/nutripoints-homeassistant/issues/18)


### Bug Fixes

* **repairs:** deduplicate contract mismatch issue ([53f5fac](https://github.com/megageek/nutripoints-homeassistant/commit/53f5facb2efcf9a166bdd24a951ac762f13d279a))

## [0.3.4](https://github.com/megageek/nutripoints-homeassistant/compare/v0.3.3...v0.3.4) (2026-07-30)


### Features

* **contract:** support stable-rw-v8 ([9d30db0](https://github.com/megageek/nutripoints-homeassistant/commit/9d30db05b40e26e50d4e82b30cc6cb7465933dab))
* **contract:** support stable-rw-v8 ([ba63242](https://github.com/megageek/nutripoints-homeassistant/commit/ba632421e21f3754e9ff9af40776cd3a1b9288e3))

## [0.3.3](https://github.com/megageek/nutripoints-homeassistant/compare/v0.3.2...v0.3.3) (2026-07-26)


### Bug Fixes

* **triggers:** support not-triggered reporter ([08c7a09](https://github.com/megageek/nutripoints-homeassistant/commit/08c7a09b000c5a07a65df7a0cbb26564594d753d))

## [0.3.2](https://github.com/megageek/nutripoints-homeassistant/compare/v0.3.1...v0.3.2) (2026-07-26)


### Bug Fixes

* **triggers:** add automation UI metadata ([f5fe5af](https://github.com/megageek/nutripoints-homeassistant/commit/f5fe5af13ed92d253ec5b846f93f0bc109710812))

## [0.3.1](https://github.com/megageek/nutripoints-homeassistant/compare/v0.3.0...v0.3.1) (2026-07-26)


### Features

* add food weighing sessions ([d426033](https://github.com/megageek/nutripoints-homeassistant/commit/d4260338b2c84bcfc38806545cf33150c6da404d)), closes [#4](https://github.com/megageek/nutripoints-homeassistant/issues/4)

## [0.3.0](https://github.com/megageek/nutripoints-homeassistant/compare/v0.2.0...v0.3.0) (2026-07-26)


### ⚠ BREAKING CHANGES

* default Nutri Points entity IDs are renamed with the server label during migration; manually customized entity IDs are preserved.

### Features

* **entity:** add device metadata and diagnostics ([140ff27](https://github.com/megageek/nutripoints-homeassistant/commit/140ff277eb0a938a0fbf8ba813f564e6f612ddd4))
* support persistent multi-server identity ([3fbc5f2](https://github.com/megageek/nutripoints-homeassistant/commit/3fbc5f237e31696ef73873646471510885d423fb))


### Bug Fixes

* **config:** harden entry lifecycle and reauthentication ([ae0065c](https://github.com/megageek/nutripoints-homeassistant/commit/ae0065c6690c7b5547693e0b3de58564a0e12a02))
* **tests:** restore reliable validation tooling ([7731a94](https://github.com/megageek/nutripoints-homeassistant/commit/7731a9434371cf646525e5f31f9fee70570bdac6))
