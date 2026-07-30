"""Test durable Nutri Points automation triggers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import voluptuous as vol

from custom_components.nutri_points.const import DOMAIN, automation_event_signal
from custom_components.nutri_points.trigger import (
    FoodLoggedTrigger,
    FoodWeighingSessionStartedTrigger,
    WeighInSummaryTrigger,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_OPTIONS
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.trigger import TriggerConfig


async def test_food_trigger_filters_and_exposes_event_payload(hass) -> None:
    """Matching events are passed directly into Home Assistant trigger data."""
    entry = SimpleNamespace(
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=SimpleNamespace(automation_events_supported=True),
    )
    hass.config_entries.async_get_entry = Mock(return_value=entry)
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
    entry = SimpleNamespace(
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=SimpleNamespace(automation_events_supported=False),
    )
    hass.config_entries.async_get_entry = Mock(return_value=entry)

    with pytest.raises(vol.Invalid, match="does not advertise"):
        await FoodLoggedTrigger.async_validate_config(hass, {CONF_OPTIONS: {"entry_id": "entry-1"}})


async def test_weighing_trigger_exposes_calculation_descriptor(hass) -> None:
    """Weighing triggers pass immutable calculation data to device automations."""
    entry = SimpleNamespace(
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=SimpleNamespace(
            automation_events_supported=True,
            weighing_sessions_supported=True,
        ),
    )
    hass.config_entries.async_get_entry = Mock(return_value=entry)
    options = {"entry_id": "entry-1", "meal_type": "breakfast"}
    validated = await FoodWeighingSessionStartedTrigger.async_validate_config(hass, {CONF_OPTIONS: options})
    trigger = FoodWeighingSessionStartedTrigger(
        hass,
        TriggerConfig(key="food_weighing_session_started", options=validated[CONF_OPTIONS]),
    )
    received = asyncio.Event()
    runner = Mock(side_effect=lambda *_args: received.set())
    remove = await trigger.async_attach_runner(runner)
    payload = {
        "id": "session-1",
        "meal_type": "breakfast",
        "nutrition_per_100g": {"protein_g": 12.5},
        "points_calculation": {"version": "food_points_macros_v1", "rounding": "half_up"},
    }

    async_dispatcher_send(
        hass,
        automation_event_signal("entry-1"),
        "food_weighing_session_started",
        payload,
    )
    await asyncio.wait_for(received.wait(), timeout=1)
    remove()

    assert runner.call_args.args[0] == payload


async def test_weigh_in_summary_trigger_exposes_total_weight_lost(hass) -> None:
    """Weigh-in summaries preserve the v8 total weight lost value."""
    entry = SimpleNamespace(
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=SimpleNamespace(automation_events_supported=True),
    )
    hass.config_entries.async_get_entry = Mock(return_value=entry)
    options = {"entry_id": "entry-1", "trigger_action": "weight_log_created"}
    validated = await WeighInSummaryTrigger.async_validate_config(hass, {CONF_OPTIONS: options})
    trigger = WeighInSummaryTrigger(
        hass,
        TriggerConfig(key="weigh_in_summary_generated", options=validated[CONF_OPTIONS]),
    )
    received = asyncio.Event()
    runner = Mock(side_effect=lambda *_args: received.set())
    remove = await trigger.async_attach_runner(runner)
    payload = {
        "event_id": 43,
        "trigger_action": "weight_log_created",
        "summary": {"total_weight_lost_kg": 12.4},
    }

    async_dispatcher_send(
        hass,
        automation_event_signal("entry-1"),
        "weigh_in_summary_generated",
        payload,
    )
    await asyncio.wait_for(received.wait(), timeout=1)
    remove()

    assert runner.call_args.args[0]["summary"]["total_weight_lost_kg"] == 12.4
