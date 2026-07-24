"""Test coordinator availability and runtime Repairs behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    coordinator = NutriPointsDataUpdateCoordinator(
        hass,
        api_client=api,
        poll_interval_seconds=60,
        config_entry=MockConfigEntry(domain=DOMAIN),
    )

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
        config_entry=MockConfigEntry(domain=DOMAIN, entry_id="entry"),
    )

    coordinator.record_poll_failure(NutriPointsAuthError("invalid"))
    issue_id = "entry_poll_invalid_auth"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    coordinator.record_poll_success()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_stream_success_does_not_clear_poll_failure(hass: HomeAssistant) -> None:
    """Recovery in one transport channel does not hide another channel's issue."""
    coordinator = NutriPointsDataUpdateCoordinator(
        hass,
        api_client=AsyncMock(),
        poll_interval_seconds=60,
        config_entry=MockConfigEntry(domain=DOMAIN, entry_id="entry"),
    )
    coordinator.record_poll_failure(NutriPointsAuthError("invalid"))

    coordinator.record_stream_success()

    assert ir.async_get(hass).async_get_issue(DOMAIN, "entry_poll_invalid_auth") is not None


async def test_coordinator_auth_failure_requests_reauthentication(hass: HomeAssistant) -> None:
    """Authentication failures are not retried as transport failures."""
    api = AsyncMock()
    api.async_get_today_status.side_effect = NutriPointsAuthError("invalid")
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = NutriPointsDataUpdateCoordinator(
        hass,
        api_client=api,
        poll_interval_seconds=60,
        config_entry=entry,
    )

    with patch.object(entry, "async_start_reauth") as start_reauth:
        await coordinator.async_refresh()

    start_reauth.assert_called_once_with(hass)
