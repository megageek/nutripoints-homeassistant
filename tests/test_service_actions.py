"""Test Nutri Points service-action lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nutri_points.const import CONF_ENTRY_ID, DOMAIN, SERVICE_SET_STEPS
from custom_components.nutri_points.data import NutriPointsRuntimeData
from custom_components.nutri_points.service_actions import async_setup_services
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError


async def test_services_register_without_loaded_entry(hass: HomeAssistant) -> None:
    """Actions remain discoverable while no config entry is loaded."""
    async_setup_services(hass)

    assert hass.services.has_service(DOMAIN, SERVICE_SET_STEPS)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_STEPS,
            {"steps": 1000},
            blocking=True,
        )


async def test_service_write_uses_loaded_runtime_and_refreshes(hass: HomeAssistant) -> None:
    """A successful write uses runtime data and requests fresh coordinator state."""
    api_client = AsyncMock()
    coordinator = AsyncMock()
    entry = MockConfigEntry(domain=DOMAIN)
    entry.runtime_data = NutriPointsRuntimeData(
        api_client=api_client,
        coordinator=coordinator,
        listener=AsyncMock(),
        automation_events_supported=False,
        runtime_metadata={},
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    async_setup_services(hass)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_STEPS,
        {"steps": 9000, "mode": "replace_total"},
        blocking=True,
    )

    api_client.async_set_steps.assert_awaited_once_with(
        steps=9000,
        mode="replace_total",
        applies_to_date=None,
    )
    coordinator.async_request_refresh.assert_awaited_once()


async def test_service_requires_entry_id_with_multiple_loaded_entries(
    hass: HomeAssistant,
) -> None:
    """Ambiguous writes are rejected and an explicit entry routes correctly."""
    entries: list[MockConfigEntry] = []
    clients: list[AsyncMock] = []
    for entry_id in ("entry-one", "entry-two"):
        api_client = AsyncMock()
        coordinator = AsyncMock()
        entry = MockConfigEntry(domain=DOMAIN, entry_id=entry_id)
        entry.runtime_data = NutriPointsRuntimeData(
            api_client=api_client,
            coordinator=coordinator,
            listener=AsyncMock(),
            automation_events_supported=False,
            runtime_metadata={},
        )
        entry.add_to_hass(hass)
        entry.mock_state(hass, ConfigEntryState.LOADED)
        entries.append(entry)
        clients.append(api_client)
    async_setup_services(hass)

    with pytest.raises(ServiceValidationError, match="Multiple"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_STEPS,
            {"steps": 1000},
            blocking=True,
        )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_STEPS,
        {
            CONF_ENTRY_ID: entries[1].entry_id,
            "steps": 2000,
        },
        blocking=True,
    )

    clients[0].async_set_steps.assert_not_awaited()
    clients[1].async_set_steps.assert_awaited_once()
