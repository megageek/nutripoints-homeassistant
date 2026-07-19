from __future__ import annotations

import voluptuous as vol

from custom_components.nutri_points.const import (
    CONF_ENTRY_ID,
    FOOD_NUTRITION_ENTRY_MODES,
    MEAL_TYPES,
    SERVICE_ATTR_APPLIES_TO_DATE,
    SERVICE_ATTR_CALORIES_KCAL,
    SERVICE_ATTR_CARBS_G,
    SERVICE_ATTR_DRINK_TYPE_ID,
    SERVICE_ATTR_DRINK_TYPE_NAME,
    SERVICE_ATTR_FAT_G,
    SERVICE_ATTR_FIBER_G,
    SERVICE_ATTR_KCAL,
    SERVICE_ATTR_LOGGED_AT,
    SERVICE_ATTR_MEAL_TYPE,
    SERVICE_ATTR_MODE,
    SERVICE_ATTR_NAME,
    SERVICE_ATTR_NUTRITION_ENTRY_MODE,
    SERVICE_ATTR_POINTS,
    SERVICE_ATTR_PRESET_ID,
    SERVICE_ATTR_PROTEIN_G,
    SERVICE_ATTR_STEPS,
    SERVICE_ATTR_VOLUME_ML,
    SERVICE_ATTR_WEIGHT_KG,
    STEP_UPDATE_MODES,
)
import homeassistant.helpers.config_validation as cv

FOOD_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_ATTR_NAME): vol.Any(cv.template, vol.All(cv.string, vol.Length(min=1, max=120))),
        vol.Optional(SERVICE_ATTR_NUTRITION_ENTRY_MODE, default="macros"): vol.In(FOOD_NUTRITION_ENTRY_MODES),
        vol.Optional(SERVICE_ATTR_PROTEIN_G): vol.Any(cv.template, vol.All(vol.Coerce(float), vol.Range(min=0))),
        vol.Optional(SERVICE_ATTR_CARBS_G): vol.Any(cv.template, vol.All(vol.Coerce(float), vol.Range(min=0))),
        vol.Optional(SERVICE_ATTR_FAT_G): vol.Any(cv.template, vol.All(vol.Coerce(float), vol.Range(min=0))),
        vol.Optional(SERVICE_ATTR_FIBER_G): vol.Any(cv.template, vol.All(vol.Coerce(float), vol.Range(min=0))),
        vol.Optional(SERVICE_ATTR_CALORIES_KCAL): vol.Any(cv.template, vol.All(vol.Coerce(float), vol.Range(min=0))),
        vol.Optional(SERVICE_ATTR_POINTS): vol.Any(cv.template, vol.All(vol.Coerce(int), vol.Range(min=0))),
        vol.Optional(SERVICE_ATTR_MEAL_TYPE): vol.Any(cv.template, vol.In(MEAL_TYPES)),
        vol.Optional(SERVICE_ATTR_APPLIES_TO_DATE): vol.Any(cv.template, cv.date),
        vol.Optional(SERVICE_ATTR_LOGGED_AT): vol.Any(cv.template, cv.datetime),
        vol.Optional(CONF_ENTRY_ID): cv.string,
    }
)

ACTIVITY_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_ATTR_KCAL): vol.Any(cv.template, vol.All(vol.Coerce(float), vol.Range(min=0))),
        vol.Optional(SERVICE_ATTR_APPLIES_TO_DATE): vol.Any(cv.template, cv.date),
        vol.Optional(SERVICE_ATTR_LOGGED_AT): vol.Any(cv.template, cv.datetime),
        vol.Optional(CONF_ENTRY_ID): cv.string,
    }
)

DRINK_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_ATTR_DRINK_TYPE_ID): vol.Any(cv.template, vol.All(vol.Coerce(int), vol.Range(min=1))),
        vol.Optional(SERVICE_ATTR_DRINK_TYPE_NAME): vol.Any(cv.template, vol.All(cv.string, vol.Length(min=1, max=80))),
        vol.Required(SERVICE_ATTR_VOLUME_ML): vol.Any(cv.template, vol.Coerce(int)),
        vol.Optional(SERVICE_ATTR_PRESET_ID): vol.Any(cv.template, vol.All(vol.Coerce(int), vol.Range(min=1))),
        vol.Optional(SERVICE_ATTR_APPLIES_TO_DATE): vol.Any(cv.template, cv.date),
        vol.Optional(SERVICE_ATTR_LOGGED_AT): vol.Any(cv.template, cv.datetime),
        vol.Optional(CONF_ENTRY_ID): cv.string,
    }
)

WEIGHT_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_ATTR_WEIGHT_KG): vol.Any(cv.template, vol.All(vol.Coerce(float), vol.Range(min=0.000001))),
        vol.Optional(SERVICE_ATTR_APPLIES_TO_DATE): vol.Any(cv.template, cv.date),
        vol.Optional(SERVICE_ATTR_LOGGED_AT): vol.Any(cv.template, cv.datetime),
        vol.Optional(CONF_ENTRY_ID): cv.string,
    }
)

STEPS_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_ATTR_STEPS): vol.Any(cv.template, vol.All(vol.Coerce(int), vol.Range(min=0))),
        vol.Optional(SERVICE_ATTR_MODE, default="replace_total"): vol.In(STEP_UPDATE_MODES),
        vol.Optional(SERVICE_ATTR_APPLIES_TO_DATE): vol.Any(cv.template, cv.date),
        vol.Optional(CONF_ENTRY_ID): cv.string,
    }
)
