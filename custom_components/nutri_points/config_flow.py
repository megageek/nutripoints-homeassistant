from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
    VERSION = 2
    MINOR_VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create the single supported Nutri Points entry."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized = _normalize_config(user_input)
                _validate_base_url(normalized[CONF_BASE_URL])
                await _async_validate(self.hass, normalized)
                return self.async_create_entry(title=f"Nutri Points ({normalized[CONF_BASE_URL]})", data=normalized)
            except (NutriPointsApiError, ValueError, KeyError) as exc:
                _apply_validation_error(errors, exc)

        return self.async_show_form(step_id="user", data_schema=_user_schema(user_input), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return NutriPointsOptionsFlow()

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],
    ) -> ConfigFlowResult:
        """Request replacement credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Validate and store a replacement API key."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            updated = {**entry.data, CONF_API_KEY: str(user_input[CONF_API_KEY]).strip()}
            try:
                await _async_validate(self.hass, updated)
            except (NutriPointsApiError, ValueError, KeyError) as exc:
                _apply_validation_error(errors, exc)
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_API_KEY: updated[CONF_API_KEY]},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Validate and update connection settings."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            updated = {
                **entry.data,
                CONF_BASE_URL: str(user_input[CONF_BASE_URL]).strip().rstrip("/"),
                CONF_VERIFY_SSL: bool(user_input[CONF_VERIFY_SSL]),
            }
            try:
                _validate_base_url(updated[CONF_BASE_URL])
                await _async_validate(self.hass, updated)
            except (NutriPointsApiError, ValueError, KeyError) as exc:
                _apply_validation_error(errors, exc)
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_BASE_URL: updated[CONF_BASE_URL],
                        CONF_VERIFY_SSL: updated[CONF_VERIFY_SSL],
                    },
                    title=f"Nutri Points ({updated[CONF_BASE_URL]})",
                )
        schema = self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Required(CONF_BASE_URL): str,
                    vol.Required(CONF_VERIFY_SSL): bool,
                }
            ),
            entry.data,
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)


class NutriPointsOptionsFlow(OptionsFlowWithReload):
    """Manage mutable polling and display options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        defaults = {
            CONF_POLL_INTERVAL_SECONDS: self.config_entry.options.get(
                CONF_POLL_INTERVAL_SECONDS,
                self.config_entry.data.get(CONF_POLL_INTERVAL_SECONDS, DEFAULT_POLL_INTERVAL_SECONDS),
            ),
            CONF_LOW_POINTS_THRESHOLD: self.config_entry.options.get(
                CONF_LOW_POINTS_THRESHOLD,
                self.config_entry.data.get(CONF_LOW_POINTS_THRESHOLD, DEFAULT_LOW_POINTS_THRESHOLD),
            ),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL_SECONDS,
                        default=defaults[CONF_POLL_INTERVAL_SECONDS],
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_POLL_INTERVAL_SECONDS, max=MAX_POLL_INTERVAL_SECONDS),
                    ),
                    vol.Required(
                        CONF_LOW_POINTS_THRESHOLD,
                        default=defaults[CONF_LOW_POINTS_THRESHOLD],
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_LOW_POINTS_THRESHOLD, max=MAX_LOW_POINTS_THRESHOLD),
                    ),
                }
            ),
        )


async def _async_validate(hass: Any, config: Mapping[str, Any]) -> None:
    client = NutriPointsApiClient(
        session=async_get_clientsession(hass),
        base_url=config[CONF_BASE_URL],
        api_key=config[CONF_API_KEY],
        verify_ssl=config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
    )
    await client.async_validate_runtime()
