"""Diagnostics support for Nutri Points."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_API_KEY
from .data import NutriPointsConfigEntry

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: NutriPointsConfigEntry,
) -> dict[str, Any]:
    """Return redacted diagnostics for a Nutri Points config entry."""
    runtime = entry.runtime_data
    metadata = runtime.runtime_metadata
    return {
        "config_entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "state": entry.state.value,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "unique_id": entry.unique_id,
        },
        "runtime": {
            "automation_events_supported": runtime.automation_events_supported,
            "weighing_sessions_supported": runtime.weighing_sessions_supported,
            "weighing_sessions": runtime.weighing_sessions.diagnostics(),
            "connection": runtime.coordinator.connection_diagnostics(),
            "metadata": {
                "api_contract_version": metadata.get("api_contract_version"),
                "capabilities": metadata.get("capabilities"),
                "version": metadata.get("version"),
                "server_uuid": metadata.get("server_uuid"),
            },
        },
    }
