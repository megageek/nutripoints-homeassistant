"""Test Nutri Points config and options flows in Home Assistant."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nutri_points import async_migrate_entry
from custom_components.nutri_points.const import (
    CONF_BASE_URL,
    CONF_LOW_POINTS_THRESHOLD,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

USER_INPUT = {
    CONF_NAME: "Home",
    CONF_BASE_URL: "http://nutri.local:8000",
    CONF_API_KEY: "npk_test",
    CONF_POLL_INTERVAL_SECONDS: 60,
    CONF_LOW_POINTS_THRESHOLD: 5,
    CONF_VERIFY_SSL: True,
}
SERVER_UUID = "8f13a050-cc4c-4f89-aaf8-5badb51cbf5d"
RUNTIME = {
    "api_contract_version": "2026-07-24.stable-rw-v5",
    "server_uuid": SERVER_UUID,
}


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """Valid server credentials create a stable config entry."""
    with patch(
        "custom_components.nutri_points.config_flow._async_validate",
        new=AsyncMock(return_value=RUNTIME),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER}, data=USER_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == SERVER_UUID


async def test_user_flow_rejects_invalid_url_before_network(hass: HomeAssistant) -> None:
    """Boundary validation rejects paths and relative URLs."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={**USER_INPUT, CONF_BASE_URL: "nutri.local/api"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}


async def test_user_flow_creates_second_server_entry(hass: HomeAssistant) -> None:
    """A different server UUID creates an independent config entry."""
    MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id=SERVER_UUID).add_to_hass(hass)

    with patch(
        "custom_components.nutri_points.config_flow._async_validate",
        new=AsyncMock(
            return_value={
                **RUNTIME,
                "server_uuid": "9d4245b1-80e2-4eb5-b174-e20795f3f2e7",
            }
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "9d4245b1-80e2-4eb5-b174-e20795f3f2e7"


async def test_options_store_only_mutable_settings(hass: HomeAssistant) -> None:
    """Options update polling behavior without changing credentials."""
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT)
    entry.add_to_hass(hass)
    options_input = {
        CONF_POLL_INTERVAL_SECONDS: 120,
        CONF_LOW_POINTS_THRESHOLD: 7,
    }

    with patch("custom_components.nutri_points.async_setup_entry", new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id, data=options_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_API_KEY] == "npk_test"
    assert entry.options == options_input


async def test_reauth_updates_only_api_key(hass: HomeAssistant) -> None:
    """Successful reauthentication replaces the stored API key."""
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT)
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    with patch(
        "custom_components.nutri_points.config_flow._async_validate",
        new=AsyncMock(return_value=RUNTIME),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "npk_replacement"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == "npk_replacement"
    assert entry.data[CONF_BASE_URL] == USER_INPUT[CONF_BASE_URL]


async def test_reconfigure_updates_connection(hass: HomeAssistant) -> None:
    """Reconfigure changes connection settings without replacing credentials."""
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )

    with patch(
        "custom_components.nutri_points.config_flow._async_validate",
        new=AsyncMock(return_value=RUNTIME),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Home",
                CONF_BASE_URL: "https://nutri.example",
                CONF_VERIFY_SSL: False,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_BASE_URL] == "https://nutri.example"
    assert entry.data[CONF_VERIFY_SSL] is False
    assert entry.data[CONF_API_KEY] == USER_INPUT[CONF_API_KEY]


async def test_user_flow_updates_existing_entry_at_new_url(hass: HomeAssistant) -> None:
    """The same server UUID at a new URL updates instead of duplicating the entry."""
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id=SERVER_UUID)
    entry.add_to_hass(hass)
    updated_input = {**USER_INPUT, CONF_BASE_URL: "https://nutri.example"}

    with (
        patch(
            "custom_components.nutri_points.config_flow._async_validate",
            new=AsyncMock(return_value=RUNTIME),
        ),
        patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=updated_input,
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_BASE_URL] == "https://nutri.example"
    assert entry.unique_id == SERVER_UUID


async def test_reconfigure_confirms_replacement_identity(hass: HomeAssistant) -> None:
    """A replacement server requires a second explicit confirmation."""
    replacement_uuid = "9d4245b1-80e2-4eb5-b174-e20795f3f2e7"
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id=SERVER_UUID)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )

    with patch(
        "custom_components.nutri_points.config_flow._async_validate",
        new=AsyncMock(return_value={**RUNTIME, "server_uuid": replacement_uuid}),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Replacement",
                CONF_BASE_URL: "https://replacement.example",
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm_identity_replacement"

    with patch.object(
        hass.config_entries,
        "async_reload",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.ABORT
    assert entry.unique_id == replacement_uuid
    assert entry.data[CONF_BASE_URL] == "https://replacement.example"
    assert entry.title == "Replacement"


async def test_reconfigure_rejects_uuid_owned_by_another_entry(
    hass: HomeAssistant,
) -> None:
    """Reconfigure cannot merge one config entry into another server identity."""
    other_uuid = "9d4245b1-80e2-4eb5-b174-e20795f3f2e7"
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id=SERVER_UUID)
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        data={**USER_INPUT, CONF_NAME: "Away", CONF_BASE_URL: "https://away.example"},
        unique_id=other_uuid,
    )
    entry.add_to_hass(hass)
    other_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )

    with patch(
        "custom_components.nutri_points.config_flow._async_validate",
        new=AsyncMock(return_value={**RUNTIME, "server_uuid": other_uuid}),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Home",
                CONF_BASE_URL: "https://away.example",
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "already_configured"}


async def test_migration_clears_url_unique_id(hass: HomeAssistant) -> None:
    """Version two migration removes mutable URL identity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={key: value for key, value in USER_INPUT.items() if key != CONF_NAME},
        unique_id="nutri_points::http://nutri.local:8000",
        version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 2
    assert entry.minor_version == 2
    assert entry.unique_id is None
    assert entry.data[CONF_NAME] == "nutri.local"
