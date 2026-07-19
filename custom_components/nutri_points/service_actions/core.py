"""Register and execute Nutri Points service actions."""

from __future__ import annotations

from typing import Any, cast

from custom_components.nutri_points.api import NutriPointsApiClient, NutriPointsApiError
from custom_components.nutri_points.const import (
    CONF_ENTRY_ID,
    DOMAIN,
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
    SERVICE_LOG_ACTIVITY,
    SERVICE_LOG_DRINK,
    SERVICE_LOG_FOOD,
    SERVICE_LOG_WEIGHT,
    SERVICE_SET_STEPS,
)
from custom_components.nutri_points.coordinator import NutriPointsDataUpdateCoordinator
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .parsing import (
    _async_parse_float,
    _async_parse_int,
    _async_parse_non_zero_int,
    _async_parse_optional_date,
    _async_parse_optional_datetime,
    _async_parse_optional_meal_type,
    _async_parse_optional_positive_int,
    _async_parse_string,
    _async_resolve_drink_type_id,
    _async_resolve_food_nutrition,
)
from .schemas import (
    ACTIVITY_SERVICE_SCHEMA,
    DRINK_SERVICE_SCHEMA,
    FOOD_SERVICE_SCHEMA,
    STEPS_SERVICE_SCHEMA,
    WEIGHT_SERVICE_SCHEMA,
)


def _resolve_entry_context(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    domain_data = hass.data.get(DOMAIN, {})
    entries: dict[str, dict[str, Any]] = domain_data.get("entries", {})
    requested_entry_id = call.data.get(CONF_ENTRY_ID)

    if requested_entry_id:
        entry_ctx = entries.get(requested_entry_id)
        if entry_ctx is None:
            raise HomeAssistantError(f"Nutri Points entry '{requested_entry_id}' is not loaded.")
        return entry_ctx

    if not entries:
        raise HomeAssistantError("Nutri Points integration is not configured.")
    if len(entries) > 1:
        raise HomeAssistantError("Multiple Nutri Points entries found. Provide 'entry_id' in the service call.")

    return next(iter(entries.values()))


async def _async_run_write(hass: HomeAssistant, call: ServiceCall, *, operation: str) -> None:
    entry_ctx = _resolve_entry_context(hass, call)
    api_client: NutriPointsApiClient = entry_ctx["api_client"]
    coordinator: NutriPointsDataUpdateCoordinator = entry_ctx["coordinator"]

    applies_to_date = await _async_parse_optional_date(
        hass,
        call.data.get(SERVICE_ATTR_APPLIES_TO_DATE),
        SERVICE_ATTR_APPLIES_TO_DATE,
    )
    logged_at = await _async_parse_optional_datetime(
        hass,
        call.data.get(SERVICE_ATTR_LOGGED_AT),
        SERVICE_ATTR_LOGGED_AT,
    )
    applies_to_date_value = applies_to_date.isoformat() if applies_to_date is not None else None

    try:
        if operation == SERVICE_LOG_FOOD:
            nutrition_payload = await _async_resolve_food_nutrition(hass, call)
            await api_client.async_log_food(
                name=await _async_parse_string(
                    hass,
                    call.data[SERVICE_ATTR_NAME],
                    SERVICE_ATTR_NAME,
                    min_length=1,
                    max_length=120,
                ),
                nutrition_entry_mode=cast(str | None, nutrition_payload.get(SERVICE_ATTR_NUTRITION_ENTRY_MODE)),
                protein_g=cast(float | None, nutrition_payload.get(SERVICE_ATTR_PROTEIN_G)),
                carbs_g=cast(float | None, nutrition_payload.get(SERVICE_ATTR_CARBS_G)),
                fat_g=cast(float | None, nutrition_payload.get(SERVICE_ATTR_FAT_G)),
                fiber_g=cast(float | None, nutrition_payload.get(SERVICE_ATTR_FIBER_G)),
                calories_kcal=cast(float | None, nutrition_payload.get(SERVICE_ATTR_CALORIES_KCAL)),
                points=cast(int | None, nutrition_payload.get(SERVICE_ATTR_POINTS)),
                meal_type=await _async_parse_optional_meal_type(hass, call.data.get(SERVICE_ATTR_MEAL_TYPE)),
                applies_to_date=applies_to_date_value,
                logged_at=logged_at,
            )
        elif operation == SERVICE_LOG_ACTIVITY:
            await api_client.async_log_activity(
                kcal=await _async_parse_float(hass, call.data[SERVICE_ATTR_KCAL], SERVICE_ATTR_KCAL, minimum=0),
                applies_to_date=applies_to_date_value,
                logged_at=logged_at,
            )
        elif operation == SERVICE_LOG_DRINK:
            await api_client.async_log_drink(
                drink_type_id=await _async_resolve_drink_type_id(
                    hass,
                    api_client,
                    drink_type_id_value=call.data.get(SERVICE_ATTR_DRINK_TYPE_ID),
                    drink_type_name_value=call.data.get(SERVICE_ATTR_DRINK_TYPE_NAME),
                ),
                volume_ml=await _async_parse_non_zero_int(
                    hass,
                    call.data[SERVICE_ATTR_VOLUME_ML],
                    SERVICE_ATTR_VOLUME_ML,
                    maximum_abs=5000,
                ),
                preset_id=await _async_parse_optional_positive_int(
                    hass,
                    call.data.get(SERVICE_ATTR_PRESET_ID),
                    SERVICE_ATTR_PRESET_ID,
                ),
                applies_to_date=applies_to_date_value,
                logged_at=logged_at,
            )
        elif operation == SERVICE_LOG_WEIGHT:
            await api_client.async_log_weight(
                weight_kg=await _async_parse_float(
                    hass,
                    call.data[SERVICE_ATTR_WEIGHT_KG],
                    SERVICE_ATTR_WEIGHT_KG,
                    minimum=0.000001,
                ),
                applies_to_date=applies_to_date_value,
                logged_at=logged_at,
            )
        elif operation == SERVICE_SET_STEPS:
            await api_client.async_set_steps(
                steps=await _async_parse_int(hass, call.data[SERVICE_ATTR_STEPS], SERVICE_ATTR_STEPS, minimum=0),
                mode=call.data[SERVICE_ATTR_MODE],
                applies_to_date=applies_to_date_value,
            )
        else:
            raise HomeAssistantError(f"Unsupported Nutri Points service operation '{operation}'.")
    except NutriPointsApiError as exc:
        raise HomeAssistantError(str(exc)) from exc

    await coordinator.async_request_refresh()


def _register_services(hass: HomeAssistant) -> None:
    async def async_handle_log_food(call: ServiceCall) -> None:
        await _async_run_write(hass, call, operation=SERVICE_LOG_FOOD)

    async def async_handle_log_activity(call: ServiceCall) -> None:
        await _async_run_write(hass, call, operation=SERVICE_LOG_ACTIVITY)

    async def async_handle_log_drink(call: ServiceCall) -> None:
        await _async_run_write(hass, call, operation=SERVICE_LOG_DRINK)

    async def async_handle_log_weight(call: ServiceCall) -> None:
        await _async_run_write(hass, call, operation=SERVICE_LOG_WEIGHT)

    async def async_handle_set_steps(call: ServiceCall) -> None:
        await _async_run_write(hass, call, operation=SERVICE_SET_STEPS)

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_FOOD,
        async_handle_log_food,
        schema=FOOD_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_ACTIVITY,
        async_handle_log_activity,
        schema=ACTIVITY_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_DRINK,
        async_handle_log_drink,
        schema=DRINK_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_WEIGHT,
        async_handle_log_weight,
        schema=WEIGHT_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_STEPS,
        async_handle_set_steps,
        schema=STEPS_SERVICE_SCHEMA,
    )


def _unregister_services(hass: HomeAssistant) -> None:
    for service in (SERVICE_LOG_FOOD, SERVICE_LOG_ACTIVITY, SERVICE_LOG_DRINK, SERVICE_LOG_WEIGHT, SERVICE_SET_STEPS):
        hass.services.async_remove(DOMAIN, service)
