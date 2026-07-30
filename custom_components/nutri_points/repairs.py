from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    NutriPointsApiClient,
    NutriPointsApiError,
    NutriPointsAuthError,
    NutriPointsContractError,
    NutriPointsHttpApiKeyForbiddenError,
    NutriPointsIdentityMismatchError,
    NutriPointsInvalidHostError,
    NutriPointsRuntimeMetadata,
    NutriPointsTlsError,
    NutriPointsUnexpectedServerError,
)
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_VERIFY_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    IDENTITY_MISMATCH_ISSUE_SUFFIX,
    RUNTIME_FAILURE_HTTP_API_KEY_FORBIDDEN,
    RUNTIME_FAILURE_IDENTITY_MISMATCH,
    RUNTIME_FAILURE_INCOMPATIBLE_CONTRACT,
    RUNTIME_FAILURE_INVALID_AUTH,
    RUNTIME_FAILURE_INVALID_HOST,
    RUNTIME_FAILURE_TRANSIENT_TRANSPORT,
    TRANSIENT_RUNTIME_ISSUE_THRESHOLD,
)


def identity_mismatch_issue_id(entry_id: str) -> str:
    """Return the stable repair issue ID for a config entry."""
    return f"{entry_id}_{IDENTITY_MISMATCH_ISSUE_SUFFIX}"


def async_create_identity_mismatch_issue(
    hass: HomeAssistant,
    *,
    entry_id: str,
    expected_uuid: str,
    observed_uuid: str,
) -> None:
    """Create a persistent, fixable server identity mismatch issue."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        identity_mismatch_issue_id(entry_id),
        data={
            "entry_id": entry_id,
            "expected_uuid": expected_uuid,
            "observed_uuid": observed_uuid,
        },
        is_fixable=True,
        is_persistent=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key=IDENTITY_MISMATCH_ISSUE_SUFFIX,
        translation_placeholders={
            "expected_uuid": expected_uuid,
            "observed_uuid": observed_uuid,
        },
    )


def classify_runtime_failure(exc: Exception) -> str:
    if isinstance(exc, NutriPointsIdentityMismatchError):
        return RUNTIME_FAILURE_IDENTITY_MISMATCH
    if isinstance(exc, NutriPointsAuthError):
        return RUNTIME_FAILURE_INVALID_AUTH
    if isinstance(exc, NutriPointsInvalidHostError):
        return RUNTIME_FAILURE_INVALID_HOST
    if isinstance(exc, NutriPointsHttpApiKeyForbiddenError):
        return RUNTIME_FAILURE_HTTP_API_KEY_FORBIDDEN
    if isinstance(exc, NutriPointsContractError):
        return RUNTIME_FAILURE_INCOMPATIBLE_CONTRACT
    if isinstance(exc, NutriPointsApiError):
        return RUNTIME_FAILURE_TRANSIENT_TRANSPORT
    return RUNTIME_FAILURE_TRANSIENT_TRANSPORT


class NutriPointsRuntimeIssueTracker:
    def __init__(
        self,
        *,
        hass: HomeAssistant,
        entry_id: str,
        scope: str,
        incompatible_contract_scopes: set[str],
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._scope = scope
        self._incompatible_contract_scopes = incompatible_contract_scopes
        self.failure_class: str | None = None
        self.failure_count = 0
        self.first_failure_at: str | None = None
        self.active_issue_id: str | None = None

    def _utc_now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def _incompatible_contract_issue_id(self) -> str:
        return f"{self._entry_id}_runtime_{RUNTIME_FAILURE_INCOMPATIBLE_CONTRACT}"

    def _issue_id(self, failure_class: str) -> str:
        if failure_class == RUNTIME_FAILURE_INCOMPATIBLE_CONTRACT:
            return self._incompatible_contract_issue_id()
        return f"{self._entry_id}_{self._scope}_{failure_class}"

    def _clear_active_issue(self) -> None:
        if self.active_issue_id is None:
            return
        if self.active_issue_id == self._incompatible_contract_issue_id():
            self._incompatible_contract_scopes.discard(self._scope)
            if self._incompatible_contract_scopes:
                self.active_issue_id = None
                return
        ir.async_delete_issue(self._hass, DOMAIN, self.active_issue_id)
        self.active_issue_id = None

    def diagnostics(self) -> dict[str, object]:
        return {
            "runtime_failure_class": self.failure_class,
            "runtime_failure_count": self.failure_count,
            "runtime_issue_active": self.active_issue_id is not None,
            "runtime_first_failure_at": self.first_failure_at,
        }

    def record_failure(self, exc: Exception) -> None:
        failure_class = classify_runtime_failure(exc)
        if failure_class == self.failure_class:
            self.failure_count += 1
        else:
            self.failure_class = failure_class
            self.failure_count = 1
            self.first_failure_at = self._utc_now_iso()

        should_raise = (
            failure_class != RUNTIME_FAILURE_TRANSIENT_TRANSPORT
            or self.failure_count >= TRANSIENT_RUNTIME_ISSUE_THRESHOLD
        )
        if should_raise:
            self._create_or_replace_issue(failure_class)

    def record_success(self) -> None:
        self._clear_active_issue()
        self.failure_class = None
        self.failure_count = 0
        self.first_failure_at = None

    def _create_or_replace_issue(self, failure_class: str) -> None:
        issue_id = self._issue_id(failure_class)
        if self.active_issue_id == issue_id:
            return
        self._clear_active_issue()
        if failure_class == RUNTIME_FAILURE_INCOMPATIBLE_CONTRACT:
            self._incompatible_contract_scopes.add(self._scope)
            for scope in ("poll", "stream"):
                ir.async_delete_issue(
                    self._hass,
                    DOMAIN,
                    f"{self._entry_id}_{scope}_{failure_class}",
                )
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING
            if failure_class == RUNTIME_FAILURE_TRANSIENT_TRANSPORT
            else ir.IssueSeverity.ERROR,
            translation_key=f"runtime_{failure_class}",
        )
        self.active_issue_id = issue_id


def _repair_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): vol.All(
                str,
                vol.Strip,
                vol.Length(min=1, max=64),
            ),
            vol.Required(CONF_BASE_URL, default=defaults.get(CONF_BASE_URL, "")): str,
            vol.Required(
                CONF_VERIFY_SSL,
                default=defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            ): bool,
        }
    )


def _validate_base_url(base_url: str) -> None:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("invalid_url")


def _repair_error(exc: Exception) -> str:
    if isinstance(exc, NutriPointsAuthError):
        return "invalid_auth"
    if isinstance(exc, NutriPointsContractError):
        return "incompatible_contract"
    if isinstance(exc, NutriPointsInvalidHostError):
        return "invalid_host"
    if isinstance(exc, NutriPointsHttpApiKeyForbiddenError):
        return "http_api_key_forbidden"
    if isinstance(exc, NutriPointsTlsError):
        return "tls_failed"
    if isinstance(exc, NutriPointsUnexpectedServerError):
        return "unexpected_server"
    if isinstance(exc, ValueError):
        return "invalid_url"
    return "cannot_connect"


class NutriPointsIdentityRepairFlow(RepairsFlow):
    """Guide explicit adoption of the server currently at a configured URL."""

    def __init__(self, *, entry_id: str, issue_id: str) -> None:
        self._entry_id = entry_id
        self._issue_id = issue_id
        self._pending_data: dict[str, Any] | None = None
        self._runtime: NutriPointsRuntimeMetadata | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Validate the replacement server connection."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="entry_missing")
        errors: dict[str, str] = {}
        if user_input is not None:
            updated = {
                **entry.data,
                CONF_NAME: str(user_input[CONF_NAME]).strip(),
                CONF_BASE_URL: str(user_input[CONF_BASE_URL]).strip().rstrip("/"),
                CONF_VERIFY_SSL: bool(user_input[CONF_VERIFY_SSL]),
            }
            try:
                _validate_base_url(updated[CONF_BASE_URL])
                client = NutriPointsApiClient(
                    session=async_get_clientsession(self.hass),
                    base_url=updated[CONF_BASE_URL],
                    api_key=updated[CONF_API_KEY],
                    verify_ssl=updated[CONF_VERIFY_SSL],
                )
                runtime = await client.async_validate_runtime()
                if runtime["server_uuid"] is None:
                    raise NutriPointsContractError("Server identity repair requires stable-rw-v5.")
                if any(
                    current_entry.entry_id != entry.entry_id and current_entry.unique_id == runtime["server_uuid"]
                    for current_entry in self.hass.config_entries.async_entries(DOMAIN)
                ):
                    errors["base"] = "already_configured"
            except (NutriPointsApiError, ValueError, KeyError) as exc:
                errors["base"] = _repair_error(exc)
            if not errors:
                self._pending_data = updated
                self._runtime = runtime
                if runtime["server_uuid"] == entry.unique_id:
                    return await self._async_finish()
                return await self.async_step_confirm()
        return self.async_show_form(
            step_id="init",
            data_schema=_repair_schema(entry.data if user_input is None else user_input),
            errors=errors,
        )

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> Any:
        """Confirm adoption of a different server identity."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="entry_missing")
        if self._runtime is None:
            return self.async_abort(reason="validation_required")
        if user_input is not None:
            return await self._async_finish()
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "expected_uuid": entry.unique_id or "unassigned",
                "observed_uuid": self._runtime["server_uuid"] or "unassigned",
            },
        )

    async def _async_finish(self) -> Any:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or self._pending_data is None or self._runtime is None:
            return self.async_abort(reason="entry_missing")
        server_uuid = self._runtime["server_uuid"]
        if server_uuid is None:
            return self.async_abort(reason="validation_required")
        self.hass.config_entries.async_update_entry(
            entry,
            data=self._pending_data,
            title=self._pending_data[CONF_NAME],
            unique_id=server_uuid,
        )
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        await self.hass.config_entries.async_reload(entry.entry_id)
        return self.async_create_entry(data={})


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for a server identity mismatch."""
    entry_id = str(data.get("entry_id", "")) if data else ""
    return NutriPointsIdentityRepairFlow(entry_id=entry_id, issue_id=issue_id)
