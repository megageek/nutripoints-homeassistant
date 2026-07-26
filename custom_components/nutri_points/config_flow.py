from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    NutriPointsApiClient,
    NutriPointsApiError,
    NutriPointsAuthError,
    NutriPointsContractError,
    NutriPointsHttpApiKeyForbiddenError,
    NutriPointsInvalidHostError,
    NutriPointsRuntimeMetadata,
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
from .utils import default_server_name


def _normalize_config(
    user_input: dict[str, Any], *, existing: Mapping[str, Any] | None = None, preserve_blank_api_key: bool = False
) -> dict[str, Any]:
    existing = existing or {}
    api_key_value = str(user_input.get(CONF_API_KEY, "")).strip()
    if preserve_blank_api_key and not api_key_value:
        api_key_value = str(existing.get(CONF_API_KEY, "")).strip()
    return {
        **existing,
        CONF_NAME: str(user_input[CONF_NAME]).strip(),
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
    default_base_url = str(defaults.get(CONF_BASE_URL, "http://localhost:8000"))
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
            vol.Required(
                CONF_NAME,
                default=defaults.get(CONF_NAME, default_server_name(default_base_url)),
            ): vol.All(str, vol.Strip, vol.Length(min=1, max=64)),
            vol.Required(CONF_BASE_URL, default=default_base_url): str,
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
    MINOR_VERSION = 2
    _pending_reconfigure: dict[str, Any]
    _pending_server_uuid: str

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create or update a UUID-identified Nutri Points server entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized = _normalize_config(user_input)
                _validate_base_url(normalized[CONF_BASE_URL])
                runtime = await _async_validate(self.hass, normalized)
                server_uuid = runtime["server_uuid"]
                if server_uuid is None:
                    errors["base"] = "identity_required"
                    raise ValueError("identity_required")
                current_entries = self._async_current_entries()
                entry = next(
                    (
                        current_entry
                        for current_entry in current_entries
                        if current_entry.unique_id == server_uuid
                        or (
                            current_entry.unique_id is None
                            and current_entry.data.get(CONF_BASE_URL) == normalized[CONF_BASE_URL]
                        )
                    ),
                    None,
                )
                if entry is not None:
                    updated = {
                        **entry.data,
                        CONF_NAME: normalized[CONF_NAME],
                        CONF_BASE_URL: normalized[CONF_BASE_URL],
                        CONF_API_KEY: normalized[CONF_API_KEY],
                        CONF_VERIFY_SSL: normalized[CONF_VERIFY_SSL],
                    }
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data=updated,
                        title=normalized[CONF_NAME],
                        unique_id=server_uuid,
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="already_configured")
                await self.async_set_unique_id(server_uuid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=normalized[CONF_NAME], data=normalized)
            except (NutriPointsApiError, ValueError, KeyError) as exc:
                if not errors:
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
                runtime = await _async_validate(self.hass, updated)
                if entry.unique_id is not None and runtime["server_uuid"] != entry.unique_id:
                    errors["base"] = "different_server_configured"
            except (NutriPointsApiError, ValueError, KeyError) as exc:
                _apply_validation_error(errors, exc)
            if not errors:
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
                CONF_NAME: str(user_input[CONF_NAME]).strip(),
                CONF_BASE_URL: str(user_input[CONF_BASE_URL]).strip().rstrip("/"),
                CONF_VERIFY_SSL: bool(user_input[CONF_VERIFY_SSL]),
            }
            try:
                _validate_base_url(updated[CONF_BASE_URL])
                runtime = await _async_validate(self.hass, updated)
                server_uuid = runtime["server_uuid"]
                if server_uuid is None:
                    errors["base"] = "identity_required"
                elif any(
                    current_entry.entry_id != entry.entry_id and current_entry.unique_id == server_uuid
                    for current_entry in self._async_current_entries()
                ):
                    errors["base"] = "already_configured"
                elif entry.unique_id is not None and server_uuid != entry.unique_id:
                    self._pending_reconfigure = updated
                    self._pending_server_uuid = server_uuid
                    return await self.async_step_confirm_identity_replacement()
                else:
                    return await self._async_finish_reconfigure(entry, updated, server_uuid)
            except (NutriPointsApiError, ValueError, KeyError) as exc:
                _apply_validation_error(errors, exc)
        schema = self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Required(CONF_NAME): vol.All(str, vol.Strip, vol.Length(min=1, max=64)),
                    vol.Required(CONF_BASE_URL): str,
                    vol.Required(CONF_VERIFY_SSL): bool,
                }
            ),
            entry.data,
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    async def async_step_confirm_identity_replacement(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Require explicit confirmation before adopting a replacement server."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return await self._async_finish_reconfigure(
                entry,
                self._pending_reconfigure,
                self._pending_server_uuid,
            )
        return self.async_show_form(
            step_id="confirm_identity_replacement",
            data_schema=vol.Schema({}),
            description_placeholders={
                "expected_uuid": entry.unique_id or "unassigned",
                "observed_uuid": self._pending_server_uuid,
            },
        )

    async def _async_finish_reconfigure(
        self,
        entry: config_entries.ConfigEntry,
        updated: dict[str, Any],
        server_uuid: str,
    ) -> ConfigFlowResult:
        self.hass.config_entries.async_update_entry(entry, unique_id=server_uuid)
        return self.async_update_reload_and_abort(
            entry,
            data_updates={
                CONF_NAME: updated[CONF_NAME],
                CONF_BASE_URL: updated[CONF_BASE_URL],
                CONF_VERIFY_SSL: updated[CONF_VERIFY_SSL],
            },
            title=updated[CONF_NAME],
        )


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


async def _async_validate(hass: Any, config: Mapping[str, Any]) -> NutriPointsRuntimeMetadata:
    client = NutriPointsApiClient(
        session=async_get_clientsession(hass),
        base_url=config[CONF_BASE_URL],
        api_key=config[CONF_API_KEY],
        verify_ssl=config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
    )
    return await client.async_validate_runtime()
