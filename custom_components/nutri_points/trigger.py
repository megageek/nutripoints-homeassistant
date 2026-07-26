"""Automation triggers backed by the Nutri Points durable event stream."""

from __future__ import annotations

from typing import Any, cast

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_OPTIONS
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.trigger import Trigger, TriggerActionRunner, TriggerConfig
from homeassistant.helpers.typing import ConfigType

from .const import AUTOMATION_EVENTS_CAPABILITY, DOMAIN, WEIGHING_SESSIONS_CAPABILITY, automation_event_signal

CONF_ENTRY_ID = "entry_id"
CONF_TRIGGER_ACTION = "trigger_action"
CONF_MEAL_TYPE = "meal_type"
ANY = "any"


class NutriPointsAutomationTrigger(Trigger):
    """Base for a durable Nutri Points automation event trigger."""

    event_name: str
    allowed_actions: tuple[str, ...]
    required_capability = AUTOMATION_EVENTS_CAPABILITY

    @classmethod
    async def async_validate_config(cls, hass: HomeAssistant, config: ConfigType) -> ConfigType:
        options_schema: dict[Any, Any] = {
            vol.Required(CONF_ENTRY_ID): cv.string,
            vol.Optional(CONF_MEAL_TYPE, default=ANY): vol.In((ANY, "breakfast", "lunch", "dinner", "snack")),
        }
        if cls.allowed_actions:
            options_schema[vol.Optional(CONF_TRIGGER_ACTION, default=ANY)] = vol.In((ANY, *cls.allowed_actions))
        schema = vol.Schema({vol.Required(CONF_OPTIONS): options_schema})
        validated = cast(ConfigType, schema(config))
        options = validated[CONF_OPTIONS]
        entry = hass.config_entries.async_get_entry(options[CONF_ENTRY_ID])
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
            or (
                cls.required_capability == AUTOMATION_EVENTS_CAPABILITY
                and not entry.runtime_data.automation_events_supported
            )
            or (
                cls.required_capability == WEIGHING_SESSIONS_CAPABILITY
                and not entry.runtime_data.weighing_sessions_supported
            )
        ):
            raise vol.Invalid("This Nutri Points entry does not advertise the required trigger capability")
        return validated

    def __init__(self, hass: HomeAssistant, config: TriggerConfig) -> None:
        super().__init__(hass, config)
        options = config.options or {}
        self._entry_id = str(options[CONF_ENTRY_ID])
        self._trigger_action = str(options.get(CONF_TRIGGER_ACTION, ANY))
        self._meal_type = str(options.get(CONF_MEAL_TYPE, ANY))

    async def async_attach_runner(self, run_action: TriggerActionRunner) -> CALLBACK_TYPE:
        @callback
        def handle_event(event_name: str, payload: dict[str, Any]) -> None:
            if event_name != self.event_name:
                return
            if self._trigger_action != ANY and payload.get(CONF_TRIGGER_ACTION) != self._trigger_action:
                return
            if self._meal_type != ANY and payload.get(CONF_MEAL_TYPE) != self._meal_type:
                return
            run_action(payload, f"Nutri Points {event_name}")

        return async_dispatcher_connect(self._hass, automation_event_signal(self._entry_id), handle_event)


class FoodLoggedTrigger(NutriPointsAutomationTrigger):
    event_name = "meal_food_logged"
    allowed_actions = (
        "food_log_created",
        "food_item_logged",
        "saved_meal_logged",
        "recipe_logged",
        "recipe_batch_logged",
    )


class WeighInSummaryTrigger(NutriPointsAutomationTrigger):
    event_name = "weigh_in_summary_generated"
    allowed_actions = ("weight_log_created", "weight_log_updated")


class RecipeBatchLabelTrigger(NutriPointsAutomationTrigger):
    event_name = "recipe_batch_label_requested"
    allowed_actions = ("recipe_batch_created", "recipe_batch_reprinted")


class FoodWeighingSessionStartedTrigger(NutriPointsAutomationTrigger):
    event_name = "food_weighing_session_started"
    allowed_actions = ()
    required_capability = WEIGHING_SESSIONS_CAPABILITY


TRIGGERS: dict[str, type[Trigger]] = {
    "food_logged": FoodLoggedTrigger,
    "food_weighing_session_started": FoodWeighingSessionStartedTrigger,
    "weigh_in_summary_generated": WeighInSummaryTrigger,
    "recipe_batch_label_requested": RecipeBatchLabelTrigger,
}


async def async_get_triggers(hass: HomeAssistant) -> dict[str, type[Trigger]]:
    """Return Nutri Points automation triggers."""
    return TRIGGERS
