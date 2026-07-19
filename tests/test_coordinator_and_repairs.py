"""Test coordinator availability and runtime Repairs behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.nutri_points.api import NutriPointsApiError, NutriPointsAuthError
from custom_components.nutri_points.const import DOMAIN
from custom_components.nutri_points.coordinator import NutriPointsDataUpdateCoordinator
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir


async def test_coordinator_keeps_dataset_availability_independent(hass: HomeAssistant) -> None:
    """A failed weight read does not hide otherwise valid day/readiness data."""
    api = AsyncMock()
    api.async_get_today_status.return_value = {"status": "ready", "remaining_points": 10}
    api.async_get_today_readiness.return_value = {"weigh_in": {"status": "up_to_date"}}
    api.async_get_weight_overview.side_effect = NutriPointsApiError("weight unavailable")
    coordinator = NutriPointsDataUpdateCoordinator(hass, api_client=api, poll_interval_seconds=60, entry_id="entry")

    await coordinator.async_refresh()
    data = coordinator.data

    assert data is not None
    assert data["status"] == "ready"
    assert coordinator.day_status_available is True
    assert coordinator.readiness_available is True
    assert coordinator.weight_available is False


async def test_runtime_auth_failure_creates_and_recovery_clears_repair(hass: HomeAssistant) -> None:
    """Persistent integration failures remain visible until a successful request."""
    coordinator = NutriPointsDataUpdateCoordinator(
        hass,
        api_client=AsyncMock(),
        poll_interval_seconds=60,
        entry_id="entry",
    )

    coordinator.record_runtime_failure(NutriPointsAuthError("invalid"))
    issue_id = "entry_invalid_auth"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    coordinator.record_runtime_success()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
