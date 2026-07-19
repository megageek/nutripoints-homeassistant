"""Test Nutri Points config and options flows in Home Assistant."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nutri_points.const import (
    CONF_BASE_URL,
    CONF_LOW_POINTS_THRESHOLD,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

USER_INPUT = {
    CONF_BASE_URL: "http://nutri.local:8000",
    CONF_API_KEY: "npk_test",
    CONF_POLL_INTERVAL_SECONDS: 60,
    CONF_LOW_POINTS_THRESHOLD: 5,
    CONF_VERIFY_SSL: True,
}


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """Valid server credentials create a stable config entry."""
    with patch("custom_components.nutri_points.config_flow._async_validate", new=AsyncMock()):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER}, data=USER_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Nutri Points (http://nutri.local:8000)"
    assert result["data"] == USER_INPUT


async def test_user_flow_rejects_invalid_url_before_network(hass: HomeAssistant) -> None:
    """Boundary validation rejects paths and relative URLs."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={**USER_INPUT, CONF_BASE_URL: "nutri.local/api"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}


async def test_options_preserve_blank_api_key(hass: HomeAssistant) -> None:
    """Leaving the replacement key blank preserves the stored credential."""
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="http://nutri.local:8000")
    entry.add_to_hass(hass)
    options_input = {**USER_INPUT, CONF_API_KEY: "", CONF_LOW_POINTS_THRESHOLD: 7}

    with patch("custom_components.nutri_points.config_flow._async_validate", new=AsyncMock()):
        result = await hass.config_entries.options.async_init(entry.entry_id, data=options_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_API_KEY] == "npk_test"
    assert entry.data[CONF_LOW_POINTS_THRESHOLD] == 7
