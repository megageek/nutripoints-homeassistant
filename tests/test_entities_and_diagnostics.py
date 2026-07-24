"""Test Nutri Points entities, devices, and diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nutri_points.api import NutriPointsApiClient
from custom_components.nutri_points.const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_LOW_POINTS_THRESHOLD,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.nutri_points.coordinator import NutriPointsEventStreamListener
from custom_components.nutri_points.diagnostics import async_get_config_entry_diagnostics
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

ENTRY_DATA = {
    CONF_BASE_URL: "http://nutri.local:8000",
    CONF_API_KEY: "npk_secret",
    CONF_POLL_INTERVAL_SECONDS: 60,
    CONF_LOW_POINTS_THRESHOLD: 5,
    CONF_VERIFY_SSL: True,
}

TODAY_DATA = {
    "status": "ready",
    "date": "2026-07-24",
    "remaining_points": 8,
    "budget_points": 20,
    "food_points": 12,
    "activity_points": 2,
    "total_drink_volume_ml": 750,
    "drink_totals": [
        {
            "drink_type_id": 1,
            "drink_type_name": "Water",
            "total_volume_ml": 750,
        }
    ],
}


async def _async_setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    with (
        patch("custom_components.nutri_points.async_get_clientsession", return_value=Mock()),
        patch.object(
            NutriPointsApiClient,
            "async_validate_runtime",
            new=AsyncMock(
                return_value={
                    "api_contract_version": "stable-rw-v4",
                    "capabilities": ["ha_automation_events_v1"],
                    "version": "1.2.3",
                }
            ),
        ),
        patch.object(NutriPointsApiClient, "async_get_today_status", new=AsyncMock(return_value=TODAY_DATA)),
        patch.object(NutriPointsApiClient, "async_get_weight_overview", new=AsyncMock(return_value={})),
        patch.object(NutriPointsApiClient, "async_get_today_readiness", new=AsyncMock(return_value={})),
        patch.object(NutriPointsEventStreamListener, "start"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_entities_keep_unique_ids_and_attach_to_device(hass: HomeAssistant) -> None:
    """Entities retain legacy identity while using translated device names."""
    entry = await _async_setup_entry(hass)

    state = hass.states.get("sensor.nutri_points_remaining_points")
    assert state is not None
    assert state.state == "8"
    assert "stream_status" not in state.attributes

    entity_entry = er.async_get(hass).async_get("sensor.nutri_points_remaining_points")
    assert entity_entry is not None
    assert entity_entry.unique_id == f"{DOMAIN}_remaining_points"

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.manufacturer == "Nutri Points"
    assert device.model == "Nutri Points Server"
    assert device.sw_version == "1.2.3"


async def test_diagnostics_redact_credentials(hass: HomeAssistant) -> None:
    """Diagnostics expose health metadata without credentials or nutrition data."""
    entry = await _async_setup_entry(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["config_entry"]["data"][CONF_API_KEY] == "**REDACTED**"
    assert diagnostics["runtime"]["metadata"]["api_contract_version"] == "stable-rw-v4"
    assert "coordinator_data" not in diagnostics
