"""Test Nutri Points entities, devices, and diagnostics."""

from __future__ import annotations

from typing import Any
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
from custom_components.nutri_points.utils import async_migrate_entity_registry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

ENTRY_DATA = {
    CONF_NAME: "Home",
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


async def _async_setup_entry(
    hass: HomeAssistant,
    *,
    name: str = "Home",
    base_url: str = "http://nutri.local:8000",
    server_uuid: str | None = None,
    today_data: dict[str, Any] | None = None,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            **ENTRY_DATA,
            CONF_NAME: name,
            CONF_BASE_URL: base_url,
        },
        title=name,
        unique_id=server_uuid,
    )
    entry.add_to_hass(hass)
    with (
        patch("custom_components.nutri_points.async_get_clientsession", return_value=Mock()),
        patch.object(
            NutriPointsApiClient,
            "async_validate_runtime",
            new=AsyncMock(
                return_value={
                    "api_contract_version": ("2026-07-24.stable-rw-v5" if server_uuid is not None else "stable-rw-v4"),
                    "server_uuid": server_uuid,
                    "capabilities": ["ha_automation_events_v1"],
                    "version": "1.2.3",
                }
            ),
        ),
        patch.object(
            NutriPointsApiClient,
            "async_get_today_status",
            new=AsyncMock(return_value=today_data or TODAY_DATA),
        ),
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

    state = hass.states.get("sensor.home_remaining_points")
    assert state is not None
    assert state.state == "8"
    assert "stream_status" not in state.attributes

    entity_entry = er.async_get(hass).async_get("sensor.home_remaining_points")
    assert entity_entry is not None
    assert entity_entry.unique_id == f"{DOMAIN}_remaining_points"

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.manufacturer == "Nutri Points"
    assert device.model == "Nutri Points Server"
    assert device.sw_version == "1.2.3"


async def test_entities_ignore_v11_food_log_estimate_provenance(hass: HomeAssistant) -> None:
    """Optional v11 food-log estimate fields do not alter exposed entity state."""
    today_data = {
        **TODAY_DATA,
        "food_logs": [
            {
                "id": 42,
                "nutrition_source": "llm_estimate",
                "estimate_confidence": "low",
                "estimate_calories_low_kcal": 1250,
                "estimate_calories_high_kcal": 1850,
                "estimate_original_description": "Chicken curry, rice, and naan",
            }
        ],
    }
    await _async_setup_entry(hass, today_data=today_data)

    state = hass.states.get("sensor.home_remaining_points")
    assert state is not None
    assert state.state == "8"
    assert "food_logs" not in state.attributes


async def test_diagnostics_redact_credentials(hass: HomeAssistant) -> None:
    """Diagnostics expose health metadata without credentials or nutrition data."""
    entry = await _async_setup_entry(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["config_entry"]["data"][CONF_API_KEY] == "**REDACTED**"
    assert diagnostics["runtime"]["metadata"]["api_contract_version"] == "stable-rw-v4"
    assert "coordinator_data" not in diagnostics


async def test_entity_registry_migration_scopes_identity_and_preserves_custom_ids(
    hass: HomeAssistant,
) -> None:
    """Default IDs gain the server label while customized IDs remain untouched."""
    server_uuid = "8f13a050-cc4c-4f89-aaf8-5badb51cbf5d"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_DATA,
        title="Home",
        unique_id=server_uuid,
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    default_entity = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{DOMAIN}_remaining_points",
        config_entry=entry,
        suggested_object_id=f"{DOMAIN}_remaining_points",
    )
    custom_entity = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{DOMAIN}_weight",
        config_entry=entry,
        suggested_object_id=f"{DOMAIN}_weight",
    )
    registry.async_update_entity(
        custom_entity.entity_id,
        new_entity_id="sensor.nutri_points_custom_weight",
    )

    async_migrate_entity_registry(hass, entry, rename_default_entity_ids=True)
    async_migrate_entity_registry(hass, entry, rename_default_entity_ids=True)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_NAME: "Renamed"},
        title="Renamed",
    )
    async_migrate_entity_registry(hass, entry, rename_default_entity_ids=True)

    migrated_default = registry.async_get("sensor.home_remaining_points")
    migrated_custom = registry.async_get("sensor.nutri_points_custom_weight")
    assert migrated_default is not None
    assert migrated_default.id == default_entity.id
    assert migrated_default.unique_id == f"{server_uuid}_remaining_points"
    assert migrated_custom is not None
    assert migrated_custom.unique_id == f"{server_uuid}_weight"


async def test_two_servers_create_distinct_entities_and_devices(
    hass: HomeAssistant,
) -> None:
    """Two server UUIDs load independent entity and device registry records."""
    home_uuid = "8f13a050-cc4c-4f89-aaf8-5badb51cbf5d"
    away_uuid = "9d4245b1-80e2-4eb5-b174-e20795f3f2e7"

    home_entry = await _async_setup_entry(hass, name="Home", server_uuid=home_uuid)
    away_entry = await _async_setup_entry(
        hass,
        name="Away",
        base_url="https://away.example",
        server_uuid=away_uuid,
    )

    registry = er.async_get(hass)
    home_entities = er.async_entries_for_config_entry(registry, home_entry.entry_id)
    away_entities = er.async_entries_for_config_entry(registry, away_entry.entry_id)
    assert {entity.unique_id for entity in home_entities}.isdisjoint(entity.unique_id for entity in away_entities)
    assert f"{home_uuid}_remaining_points" in {entity.unique_id for entity in home_entities}
    assert f"{away_uuid}_remaining_points" in {entity.unique_id for entity in away_entities}

    device_registry = dr.async_get(hass)
    home_device = device_registry.async_get_device(identifiers={(DOMAIN, home_entry.entry_id)})
    away_device = device_registry.async_get_device(identifiers={(DOMAIN, away_entry.entry_id)})
    assert home_device is not None
    assert away_device is not None
    assert home_device.name == "Home"
    assert away_device.name == "Away"
