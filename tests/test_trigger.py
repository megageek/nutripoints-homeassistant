"""Test durable Nutri Points automation triggers."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest
import voluptuous as vol

from custom_components.nutri_points.const import DOMAIN, automation_event_signal
from custom_components.nutri_points.trigger import FoodLoggedTrigger
from homeassistant.const import CONF_OPTIONS
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.trigger import TriggerConfig


async def test_food_trigger_filters_and_exposes_event_payload(hass) -> None:
    """Matching events are passed directly into Home Assistant trigger data."""
    hass.data[DOMAIN] = {
        "entries": {"entry-1": {"automation_events_supported": True}},
    }
    options = {"entry_id": "entry-1", "trigger_action": "food_item_logged", "meal_type": "lunch"}
    validated = await FoodLoggedTrigger.async_validate_config(hass, {CONF_OPTIONS: options})
    trigger = FoodLoggedTrigger(hass, TriggerConfig(key="food_logged", options=validated[CONF_OPTIONS]))
    received = asyncio.Event()
    runner = Mock(side_effect=lambda *_args: received.set())
    remove = await trigger.async_attach_runner(runner)

    async_dispatcher_send(
        hass,
        automation_event_signal("entry-1"),
        "meal_food_logged",
        {"event_id": 42, "trigger_action": "food_item_logged", "meal_type": "lunch"},
    )
    await asyncio.wait_for(received.wait(), timeout=1)
    remove()

    assert runner.call_args.args[0]["event_id"] == 42


async def test_trigger_rejects_server_without_capability(hass) -> None:
    """Triggers cannot attach to older contract generations."""
    hass.data[DOMAIN] = {"entries": {"entry-1": {"automation_events_supported": False}}}

    with pytest.raises(vol.Invalid, match="does not advertise"):
        await FoodLoggedTrigger.async_validate_config(hass, {CONF_OPTIONS: {"entry_id": "entry-1"}})
