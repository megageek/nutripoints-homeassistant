from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from aiohttp import ClientSession
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback

from .api import (
    NutriPointsApiClient,
    NutriPointsApiError,
    NutriPointsAuthError,
    NutriPointsContractError,
    NutriPointsHttpApiKeyForbiddenError,
    NutriPointsInvalidHostError,
    NutriPointsTlsError,
    NutriPointsUnexpectedServerError,
)
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_LOW_POINTS_THRESHOLD,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_VERIFY_SSL,
    DEFAULT_LOW_POINTS_THRESHOLD,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MAX_LOW_POINTS_THRESHOLD,
    MAX_POLL_INTERVAL_SECONDS,
    MIN_LOW_POINTS_THRESHOLD,
    MIN_POLL_INTERVAL_SECONDS,
)


def _normalize_config(
    user_input: dict[str, Any], *, existing: Mapping[str, Any] | None = None, preserve_blank_api_key: bool = False
) -> dict[str, Any]:
    existing = existing or {}
    api_key_value = str(user_input.get(CONF_API_KEY, "")).strip()
    if preserve_blank_api_key and not api_key_value:
        api_key_value = str(existing.get(CONF_API_KEY, "")).strip()
    return {
        **existing,
        CONF_BASE_URL: str(user_input[CONF_BASE_URL]).strip().rstrip("/"),
        CONF_API_KEY: api_key_value,
        CONF_POLL_INTERVAL_SECONDS: int(user_input[CONF_POLL_INTERVAL_SECONDS]),
        CONF_LOW_POINTS_THRESHOLD: int(user_input[CONF_LOW_POINTS_THRESHOLD]),
        CONF_VERIFY_SSL: bool(user_input[CONF_VERIFY_SSL]),
    }


def _validate_base_url(base_url: str) -> None:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("base_url_scheme")
    if not parsed.netloc:
        raise ValueError("base_url_host")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url_extra_parts")
    if parsed.path not in {"", "/"}:
        raise ValueError("base_url_path")


def _user_schema(defaults: dict[str, Any] | None = None, *, api_key_required: bool = True) -> vol.Schema:
    defaults = defaults or {}
    api_key_field = (
        vol.Required(CONF_API_KEY, default=defaults.get(CONF_API_KEY, ""))
        if api_key_required
        else vol.Optional(
            CONF_API_KEY,
            default=defaults.get(CONF_API_KEY, ""),
        )
    )
    return vol.Schema(
        {
            vol.Required(CONF_BASE_URL, default=defaults.get(CONF_BASE_URL, "http://localhost:8000")): str,
            api_key_field: str,
            vol.Required(
                CONF_POLL_INTERVAL_SECONDS,
                default=defaults.get(
                    CONF_POLL_INTERVAL_SECONDS, defaults.get(CONF_SCAN_INTERVAL, DEFAULT_POLL_INTERVAL_SECONDS)
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL_SECONDS, max=MAX_POLL_INTERVAL_SECONDS)),
            vol.Required(
                CONF_LOW_POINTS_THRESHOLD,
                default=defaults.get(CONF_LOW_POINTS_THRESHOLD, DEFAULT_LOW_POINTS_THRESHOLD),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_LOW_POINTS_THRESHOLD, max=MAX_LOW_POINTS_THRESHOLD)),
            vol.Required(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)): bool,
        }
    )


def _unique_id_for_base_url(base_url: str) -> str:
    return f"nutri_points::{base_url}"


def _apply_validation_error(errors: dict[str, str], exc: Exception) -> None:
    if isinstance(exc, NutriPointsAuthError):
        errors["base"] = "invalid_auth"
    elif isinstance(exc, NutriPointsContractError):
        errors["base"] = "incompatible_contract"
    elif isinstance(exc, NutriPointsInvalidHostError):
        errors["base"] = "invalid_host"
    elif isinstance(exc, NutriPointsHttpApiKeyForbiddenError):
        errors["base"] = "http_api_key_forbidden"
    elif isinstance(exc, NutriPointsTlsError):
        errors["base"] = "tls_failed"
    elif isinstance(exc, NutriPointsUnexpectedServerError):
        errors["base"] = "unexpected_server"
    elif isinstance(exc, NutriPointsApiError):
        errors["base"] = "cannot_connect"
    elif isinstance(exc, ValueError) and str(exc).startswith("base_url_"):
        errors["base"] = "invalid_url"
    else:
        errors.setdefault("base", "invalid_input")


class NutriPointsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized = _normalize_config(user_input)
                _validate_base_url(normalized[CONF_BASE_URL])
                await self.async_set_unique_id(_unique_id_for_base_url(normalized[CONF_BASE_URL]))
                self._abort_if_unique_id_configured()
                await _async_validate(normalized)
                return self.async_create_entry(title=f"Nutri Points ({normalized[CONF_BASE_URL]})", data=normalized)
            except (NutriPointsApiError, ValueError, KeyError) as exc:
                _apply_validation_error(errors, exc)

        return self.async_show_form(step_id="user", data_schema=_user_schema(user_input), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return NutriPointsOptionsFlow(config_entry)


class NutriPointsOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized = _normalize_config(
                    user_input,
                    existing=self._config_entry.data,
                    preserve_blank_api_key=True,
                )
                _validate_base_url(normalized[CONF_BASE_URL])
                duplicate = next(
                    (
                        entry
                        for entry in self.hass.config_entries.async_entries(DOMAIN)
                        if entry.entry_id != self._config_entry.entry_id
                        and entry.unique_id == _unique_id_for_base_url(normalized[CONF_BASE_URL])
                    ),
                    None,
                )
                if duplicate is not None:
                    errors["base"] = "already_configured"
                    raise ValueError("duplicate_base_url")
                await _async_validate(normalized)
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data=normalized,
                    title=f"Nutri Points ({normalized[CONF_BASE_URL]})",
                    unique_id=_unique_id_for_base_url(normalized[CONF_BASE_URL]),
                )
                return self.async_create_entry(title="", data={})
            except (NutriPointsApiError, ValueError, KeyError) as exc:
                _apply_validation_error(errors, exc)

        defaults = {
            CONF_BASE_URL: self._config_entry.data.get(CONF_BASE_URL, "http://localhost:8000"),
            CONF_API_KEY: "",
            CONF_POLL_INTERVAL_SECONDS: self._config_entry.data.get(
                CONF_POLL_INTERVAL_SECONDS, DEFAULT_POLL_INTERVAL_SECONDS
            ),
            CONF_LOW_POINTS_THRESHOLD: self._config_entry.data.get(
                CONF_LOW_POINTS_THRESHOLD, DEFAULT_LOW_POINTS_THRESHOLD
            ),
            CONF_VERIFY_SSL: self._config_entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=_user_schema(defaults, api_key_required=False),
            errors=errors,
        )


async def _async_validate(config: dict[str, Any]) -> None:
    async with ClientSession() as session:
        client = NutriPointsApiClient(
            session=session,
            base_url=config[CONF_BASE_URL],
            api_key=config[CONF_API_KEY],
            verify_ssl=config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
        )
        await client.async_validate_runtime()
