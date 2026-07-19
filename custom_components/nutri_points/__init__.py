"""Set up the Nutri Points integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NutriPointsApiClient
from .const import CONF_API_KEY, CONF_BASE_URL, CONF_POLL_INTERVAL_SECONDS, CONF_VERIFY_SSL, DOMAIN, PLATFORMS
from .coordinator import NutriPointsDataUpdateCoordinator, NutriPointsEventStreamListener
from .service_actions import _register_services, _unregister_services

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Initialize domain-level integration state."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["logger"] = _LOGGER
    hass.data[DOMAIN].setdefault("entries", {})
    hass.data[DOMAIN].setdefault("services_registered", False)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Nutri Points config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("entries", {})
    hass.data[DOMAIN]["logger"] = _LOGGER

    api_client = NutriPointsApiClient(
        session=async_get_clientsession(hass),
        base_url=entry.data[CONF_BASE_URL],
        api_key=entry.data[CONF_API_KEY],
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, True),
    )
    coordinator = NutriPointsDataUpdateCoordinator(
        hass,
        api_client=api_client,
        poll_interval_seconds=entry.data.get(CONF_POLL_INTERVAL_SECONDS, entry.data.get(CONF_SCAN_INTERVAL, 60)),
        entry_id=entry.entry_id,
    )
    await coordinator.async_config_entry_first_refresh()

    listener = NutriPointsEventStreamListener(
        api_client=api_client,
        coordinator=coordinator,
        on_day_status_changed=coordinator.async_request_refresh,
        logger=_LOGGER,
    )
    listener.start()
    hass.data[DOMAIN]["entries"][entry.entry_id] = {
        "api_client": api_client,
        "coordinator": coordinator,
        "listener": listener,
    }
    entry.async_on_unload(entry.add_update_listener(_async_handle_entry_update))

    if not hass.data[DOMAIN].get("services_registered"):
        _register_services(hass)
        hass.data[DOMAIN]["services_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Nutri Points config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    entry_map = hass.data.get(DOMAIN, {}).get("entries", {})
    entry_context = entry_map.pop(entry.entry_id, None)
    if entry_context is not None and (listener := entry_context.get("listener")) is not None:
        await listener.stop()
    if not entry_map:
        _unregister_services(hass)
        hass.data[DOMAIN]["services_registered"] = False
    return True


async def _async_handle_entry_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
