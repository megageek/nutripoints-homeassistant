"""Set up the Nutri Points integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NutriPointsApiClient, NutriPointsApiError, NutriPointsAuthError
from .const import (
    AUTOMATION_EVENTS_CAPABILITY,
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import NutriPointsDataUpdateCoordinator, NutriPointsEventStreamListener
from .data import NutriPointsConfigEntry, NutriPointsRuntimeData
from .service_actions import async_setup_services

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
    coordinator = NutriPointsDataUpdateCoordinator(
        hass,
        api_client=api_client,
        poll_interval_seconds=entry.options.get(
            CONF_POLL_INTERVAL_SECONDS,
            entry.data.get(CONF_POLL_INTERVAL_SECONDS, entry.data.get(CONF_SCAN_INTERVAL, 60)),
        ),
        config_entry=entry,
    )
    await coordinator.async_config_entry_first_refresh()

    listener = NutriPointsEventStreamListener(
        api_client=api_client,
        coordinator=coordinator,
        on_day_status_changed=coordinator.async_request_refresh,
        logger=_LOGGER,
        hass=hass,
        entry_id=entry.entry_id,
    )
    entry.runtime_data = NutriPointsRuntimeData(
        api_client=api_client,
        coordinator=coordinator,
        listener=listener,
        automation_events_supported=AUTOMATION_EVENTS_CAPABILITY in runtime.get("capabilities", []),
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
    """Migrate legacy URL-derived config entry identity."""
    if entry.version > 2:
        return False
    if entry.version < 2 or entry.unique_id is not None:
        hass.config_entries.async_update_entry(entry, unique_id=None, version=2, minor_version=1)
    return True
