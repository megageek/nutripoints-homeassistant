"""Test coordinator availability and runtime Repairs behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nutri_points.api import (
    NutriPointsApiError,
    NutriPointsAuthError,
    NutriPointsIdentityMismatchError,
)
from custom_components.nutri_points.const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
    IDENTITY_MISMATCH_ISSUE_SUFFIX,
)
from custom_components.nutri_points.coordinator import NutriPointsDataUpdateCoordinator, NutriPointsIdentityGuard
from custom_components.nutri_points.repairs import (
    NutriPointsIdentityRepairFlow,
    async_create_identity_mismatch_issue,
    identity_mismatch_issue_id,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
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

    with patch.object(entry, "async_start_reauth_if_available") as start_reauth:
        await coordinator.async_refresh()

    start_reauth.assert_called_once_with(hass)


async def test_coordinator_latches_identity_mismatch_and_creates_repair(
    hass: HomeAssistant,
) -> None:
    """A replacement server stops data reads and creates one persistent repair."""
    expected_uuid = "8f13a050-cc4c-4f89-aaf8-5badb51cbf5d"
    observed_uuid = "9d4245b1-80e2-4eb5-b174-e20795f3f2e7"
    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry", unique_id=expected_uuid)
    entry.add_to_hass(hass)
    api = AsyncMock()
    api.async_validate_identity.side_effect = NutriPointsIdentityMismatchError(
        expected_uuid,
        observed_uuid,
    )
    guard = NutriPointsIdentityGuard(hass=hass, entry=entry)
    coordinator = NutriPointsDataUpdateCoordinator(
        hass,
        api_client=api,
        poll_interval_seconds=60,
        config_entry=entry,
        identity_guard=guard,
    )

    with patch.object(hass.config_entries, "async_unload", new=AsyncMock(return_value=True)):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    assert guard.mismatch is not None
    assert api.async_get_today_status.await_count == 0
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN,
        f"entry_{IDENTITY_MISMATCH_ISSUE_SUFFIX}",
    )
    assert issue is not None
    assert issue.is_fixable is True
    assert issue.is_persistent is True


async def test_identity_repair_confirms_and_adopts_replacement(
    hass: HomeAssistant,
) -> None:
    """The repair wizard validates and explicitly adopts a replacement UUID."""
    expected_uuid = "8f13a050-cc4c-4f89-aaf8-5badb51cbf5d"
    observed_uuid = "9d4245b1-80e2-4eb5-b174-e20795f3f2e7"
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry",
        unique_id=expected_uuid,
        data={
            CONF_NAME: "Old",
            CONF_BASE_URL: "http://old.example",
            CONF_API_KEY: "npk_test",
            CONF_VERIFY_SSL: True,
        },
    )
    entry.add_to_hass(hass)
    issue_id = identity_mismatch_issue_id(entry.entry_id)
    async_create_identity_mismatch_issue(
        hass,
        entry_id=entry.entry_id,
        expected_uuid=expected_uuid,
        observed_uuid=observed_uuid,
    )
    flow = NutriPointsIdentityRepairFlow(entry_id=entry.entry_id, issue_id=issue_id)
    flow.hass = hass

    with (
        patch("custom_components.nutri_points.repairs.async_get_clientsession"),
        patch(
            "custom_components.nutri_points.repairs.NutriPointsApiClient.async_validate_runtime",
            new=AsyncMock(
                return_value={
                    "api_contract_version": "2026-07-24.stable-rw-v5",
                    "server_uuid": observed_uuid,
                }
            ),
        ),
    ):
        result = await flow.async_step_init(
            {
                CONF_NAME: "Replacement",
                CONF_BASE_URL: "https://replacement.example",
                CONF_VERIFY_SSL: False,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    with patch.object(
        hass.config_entries,
        "async_reload",
        new=AsyncMock(return_value=True),
    ):
        result = await flow.async_step_confirm({})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.unique_id == observed_uuid
    assert entry.data[CONF_BASE_URL] == "https://replacement.example"
    assert entry.data[CONF_API_KEY] == "npk_test"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
