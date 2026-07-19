"""Parse and validate templated service-action values."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import voluptuous as vol

from custom_components.nutri_points.api import NutriPointsApiClient, NutriPointsApiError
from custom_components.nutri_points.const import (
    MEAL_TYPES,
    SERVICE_ATTR_CALORIES_KCAL,
    SERVICE_ATTR_CARBS_G,
    SERVICE_ATTR_DRINK_TYPE_ID,
    SERVICE_ATTR_DRINK_TYPE_NAME,
    SERVICE_ATTR_FAT_G,
    SERVICE_ATTR_FIBER_G,
    SERVICE_ATTR_MEAL_TYPE,
    SERVICE_ATTR_NUTRITION_ENTRY_MODE,
    SERVICE_ATTR_POINTS,
    SERVICE_ATTR_PROTEIN_G,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.template import Template


async def _async_render_service_value(hass: HomeAssistant, value: Any, field: str) -> Any:
    if not isinstance(value, Template):
        return value
    try:
        rendered = value.async_render(parse_result=False)
    except Exception as exc:  # pragma: no cover - defensive for HA template runtime errors
        raise HomeAssistantError(f"Invalid template for '{field}': {exc}") from exc
    return rendered.strip() if isinstance(rendered, str) else rendered


async def _async_parse_float(
    hass: HomeAssistant,
    value: Any,
    field: str,
    *,
    minimum: float,
) -> float:
    rendered = await _async_render_service_value(hass, value, field)
    try:
        parsed = vol.Coerce(float)(rendered)
    except (TypeError, ValueError, vol.Invalid) as exc:
        raise HomeAssistantError(f"'{field}' must resolve to a number.") from exc
    if parsed < minimum:
        raise HomeAssistantError(f"'{field}' must be >= {minimum}.")
    return parsed


async def _async_parse_int(
    hass: HomeAssistant,
    value: Any,
    field: str,
    *,
    minimum: int,
) -> int:
    rendered = await _async_render_service_value(hass, value, field)
    try:
        parsed = vol.Coerce(int)(rendered)
    except (TypeError, ValueError, vol.Invalid) as exc:
        raise HomeAssistantError(f"'{field}' must resolve to an integer.") from exc
    if parsed < minimum:
        raise HomeAssistantError(f"'{field}' must be >= {minimum}.")
    return parsed


async def _async_parse_optional_positive_int(
    hass: HomeAssistant,
    value: Any,
    field: str,
) -> int | None:
    if value is None:
        return None
    return await _async_parse_int(hass, value, field, minimum=1)


async def _async_parse_string(
    hass: HomeAssistant,
    value: Any,
    field: str,
    *,
    min_length: int = 0,
    max_length: int | None = None,
) -> str:
    rendered = await _async_render_service_value(hass, value, field)
    try:
        parsed = cv.string(rendered).strip()
    except (TypeError, ValueError, vol.Invalid) as exc:
        raise HomeAssistantError(f"'{field}' must resolve to text.") from exc
    if len(parsed) < min_length:
        raise HomeAssistantError(f"'{field}' must be at least {min_length} character(s).")
    if max_length is not None and len(parsed) > max_length:
        raise HomeAssistantError(f"'{field}' must be {max_length} characters or fewer.")
    return parsed


async def _async_parse_optional_date(hass: HomeAssistant, value: Any, field: str) -> date | None:
    if value is None:
        return None
    rendered = await _async_render_service_value(hass, value, field)
    try:
        return cv.date(rendered)
    except vol.Invalid as exc:
        raise HomeAssistantError(f"'{field}' must resolve to a date (YYYY-MM-DD).") from exc


async def _async_parse_optional_datetime(hass: HomeAssistant, value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    rendered = await _async_render_service_value(hass, value, field)
    try:
        return cv.datetime(rendered)
    except vol.Invalid as exc:
        raise HomeAssistantError(f"'{field}' must resolve to an ISO datetime value.") from exc


async def _async_parse_optional_meal_type(hass: HomeAssistant, value: Any) -> str | None:
    if value is None:
        return None
    parsed = await _async_parse_string(hass, value, SERVICE_ATTR_MEAL_TYPE, min_length=1)
    if parsed not in MEAL_TYPES:
        allowed = ", ".join(MEAL_TYPES)
        raise HomeAssistantError(f"'{SERVICE_ATTR_MEAL_TYPE}' must be one of: {allowed}.")
    return parsed


async def _async_resolve_food_nutrition(hass: HomeAssistant, call: ServiceCall) -> dict[str, float | int | str]:
    nutrition_entry_mode = call.data[SERVICE_ATTR_NUTRITION_ENTRY_MODE]
    payload: dict[str, float | int | str] = {"nutrition_entry_mode": nutrition_entry_mode}
    if nutrition_entry_mode == "calories":
        if SERVICE_ATTR_CALORIES_KCAL not in call.data:
            raise HomeAssistantError(
                f"'{SERVICE_ATTR_CALORIES_KCAL}' is required when nutrition_entry_mode is 'calories'."
            )
        payload[SERVICE_ATTR_CALORIES_KCAL] = await _async_parse_float(
            hass,
            call.data[SERVICE_ATTR_CALORIES_KCAL],
            SERVICE_ATTR_CALORIES_KCAL,
            minimum=0,
        )
        return payload
    if nutrition_entry_mode == "points":
        if SERVICE_ATTR_POINTS not in call.data:
            raise HomeAssistantError(f"'{SERVICE_ATTR_POINTS}' is required when nutrition_entry_mode is 'points'.")
        payload[SERVICE_ATTR_POINTS] = await _async_parse_int(
            hass,
            call.data[SERVICE_ATTR_POINTS],
            SERVICE_ATTR_POINTS,
            minimum=0,
        )
        return payload

    for field in (SERVICE_ATTR_PROTEIN_G, SERVICE_ATTR_CARBS_G, SERVICE_ATTR_FAT_G, SERVICE_ATTR_FIBER_G):
        if field not in call.data:
            raise HomeAssistantError(f"'{field}' is required when nutrition_entry_mode is 'macros'.")
        payload[field] = await _async_parse_float(hass, call.data[field], field, minimum=0)
    return payload


async def _async_parse_non_zero_int(
    hass: HomeAssistant,
    value: Any,
    field: str,
    *,
    maximum_abs: int | None = None,
) -> int:
    parsed = await _async_parse_int(hass, value, field, minimum=-5000)
    if parsed == 0:
        raise HomeAssistantError(f"'{field}' must not be 0.")
    if maximum_abs is not None and abs(parsed) > maximum_abs:
        raise HomeAssistantError(f"'{field}' magnitude must be <= {maximum_abs}.")
    return parsed


async def _async_resolve_drink_type_id(
    hass: HomeAssistant,
    api_client: NutriPointsApiClient,
    *,
    drink_type_id_value: Any,
    drink_type_name_value: Any,
) -> int:
    drink_type_id = await _async_parse_optional_positive_int(hass, drink_type_id_value, SERVICE_ATTR_DRINK_TYPE_ID)
    drink_type_name = None
    if drink_type_name_value is not None:
        drink_type_name = await _async_parse_string(
            hass,
            drink_type_name_value,
            SERVICE_ATTR_DRINK_TYPE_NAME,
            min_length=1,
            max_length=80,
        )

    if (drink_type_id is None) == (drink_type_name is None):
        raise HomeAssistantError(
            f"Provide exactly one of '{SERVICE_ATTR_DRINK_TYPE_ID}' or '{SERVICE_ATTR_DRINK_TYPE_NAME}'."
        )

    if drink_type_id is not None:
        return drink_type_id

    try:
        settings = await api_client.async_get_drink_settings()
    except NutriPointsApiError as exc:
        raise HomeAssistantError(str(exc)) from exc

    drink_types = settings.get("drink_types") if isinstance(settings, dict) else []
    if not isinstance(drink_types, list):
        raise HomeAssistantError("Nutri Points returned invalid drink settings data.")

    normalized_name = (drink_type_name or "").casefold()
    matches = [
        item
        for item in drink_types
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and item["name"].strip().casefold() == normalized_name
    ]
    if not matches:
        raise HomeAssistantError(f"Drink type '{drink_type_name}' was not found.")
    if len(matches) > 1:
        raise HomeAssistantError(
            f"Drink type name '{drink_type_name}' is ambiguous. Use '{SERVICE_ATTR_DRINK_TYPE_ID}' instead."
        )
    resolved_id = matches[0].get("id")
    if not isinstance(resolved_id, int) or resolved_id < 1:
        raise HomeAssistantError("Resolved drink type id is invalid.")
    return resolved_id
