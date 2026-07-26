"""Set up the Nutri Points integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NutriPointsApiClient, NutriPointsApiError, NutriPointsAuthError, NutriPointsIdentityMismatchError
from .const import (
    AUTOMATION_EVENTS_CAPABILITY,
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
    WEIGHING_SESSIONS_CAPABILITY,
)
from .coordinator import NutriPointsDataUpdateCoordinator, NutriPointsEventStreamListener, NutriPointsIdentityGuard
from .data import NutriPointsConfigEntry, NutriPointsRuntimeData
from .repairs import async_create_identity_mismatch_issue
from .service_actions import async_setup_services
from .utils import async_migrate_entity_registry, default_server_name
from .weighing_sessions import NutriPointsWeighingSessionManager

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Initialize domain-level integration state."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["logger"] = _LOGGER
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NutriPointsConfigEntry) -> bool:
    """Set up a Nutri Points config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["logger"] = _LOGGER

    api_client = NutriPointsApiClient(
        session=async_get_clientsession(hass),
        base_url=entry.data[CONF_BASE_URL],
        api_key=entry.data[CONF_API_KEY],
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, True),
    )
    try:
        runtime = await api_client.async_validate_runtime()
    except NutriPointsAuthError as exc:
        raise ConfigEntryAuthFailed(str(exc)) from exc
    except NutriPointsApiError as exc:
        raise ConfigEntryNotReady(str(exc)) from exc
    server_uuid = runtime["server_uuid"]
    if entry.unique_id is None and server_uuid is not None:
        hass.config_entries.async_update_entry(entry, unique_id=server_uuid)
    elif entry.unique_id is not None:
        if server_uuid is None:
            raise ConfigEntryError("The configured Nutri Points identity requires a stable-rw-v5 server.")
        if server_uuid != entry.unique_id:
            mismatch = NutriPointsIdentityMismatchError(entry.unique_id, server_uuid)
            async_create_identity_mismatch_issue(
                hass,
                entry_id=entry.entry_id,
                expected_uuid=mismatch.expected_uuid,
                observed_uuid=mismatch.observed_uuid,
            )
            raise ConfigEntryError(str(mismatch))
    async_migrate_entity_registry(hass, entry, rename_default_entity_ids=True)
    identity_guard = NutriPointsIdentityGuard(hass=hass, entry=entry)
    coordinator = NutriPointsDataUpdateCoordinator(
        hass,
        api_client=api_client,
        poll_interval_seconds=entry.options.get(
            CONF_POLL_INTERVAL_SECONDS,
            entry.data.get(CONF_POLL_INTERVAL_SECONDS, entry.data.get(CONF_SCAN_INTERVAL, 60)),
        ),
        config_entry=entry,
        identity_guard=identity_guard,
    )
    await coordinator.async_config_entry_first_refresh()
    weighing_sessions_supported = WEIGHING_SESSIONS_CAPABILITY in runtime.get("capabilities", [])
    weighing_sessions = NutriPointsWeighingSessionManager(hass, entry.entry_id, api_client)
    await weighing_sessions.async_initialize(refresh=weighing_sessions_supported)

    listener = NutriPointsEventStreamListener(
        api_client=api_client,
        coordinator=coordinator,
        on_day_status_changed=coordinator.async_request_refresh,
        logger=_LOGGER,
        hass=hass,
        entry_id=entry.entry_id,
        expected_server_uuid=entry.unique_id,
        identity_guard=identity_guard,
        on_weighing_session_started=weighing_sessions.async_handle_started,
    )
    entry.runtime_data = NutriPointsRuntimeData(
        api_client=api_client,
        coordinator=coordinator,
        listener=listener,
        automation_events_supported=AUTOMATION_EVENTS_CAPABILITY in runtime.get("capabilities", []),
        weighing_sessions_supported=weighing_sessions_supported,
        weighing_sessions=weighing_sessions,
        runtime_metadata=runtime,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    listener.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NutriPointsConfigEntry) -> bool:
    """Unload a Nutri Points config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.listener.stop()
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy identity and add a human-readable server label."""
    if entry.version > 2:
        return False
    legacy_url_identity = entry.unique_id is not None and entry.unique_id.startswith(f"{DOMAIN}::")
    if entry.version < 2 or entry.minor_version < 2 or legacy_url_identity:
        data = dict(entry.data)
        name = str(data.get(CONF_NAME) or default_server_name(str(data[CONF_BASE_URL]))).strip()
        data[CONF_NAME] = name
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            title=name,
            unique_id=None if legacy_url_identity else entry.unique_id,
            version=2,
            minor_version=2,
        )
    return True
