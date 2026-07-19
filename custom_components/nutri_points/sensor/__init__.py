from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from custom_components.nutri_points.const import ATTR_LAST_ERROR, DOMAIN
from custom_components.nutri_points.coordinator import NutriPointsDataUpdateCoordinator
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity


@dataclass(frozen=True, kw_only=True)
class NutriSensorDescription(SensorEntityDescription):
    source_key: str


SENSOR_DESCRIPTIONS: tuple[NutriSensorDescription, ...] = (
    NutriSensorDescription(
        key="remaining_points",
        name="Nutri Remaining Points",
        icon="mdi:counter",
        source_key="remaining_points",
        native_unit_of_measurement="points",
    ),
    NutriSensorDescription(
        key="budget_points",
        name="Nutri Budget Points",
        icon="mdi:target",
        source_key="budget_points",
        native_unit_of_measurement="points",
    ),
    NutriSensorDescription(
        key="food_points",
        name="Nutri Food Points",
        icon="mdi:food-apple",
        source_key="food_points",
        native_unit_of_measurement="points",
    ),
    NutriSensorDescription(
        key="activity_points",
        name="Nutri Activity Points",
        icon="mdi:run",
        source_key="activity_points",
        native_unit_of_measurement="points",
    ),
    NutriSensorDescription(
        key="total_drink_volume_ml",
        name="Nutri Drink Volume",
        icon="mdi:cup-water",
        source_key="total_drink_volume_ml",
        native_unit_of_measurement="ml",
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: NutriPointsDataUpdateCoordinator = hass.data[DOMAIN]["entries"][entry.entry_id]["coordinator"]
    known_drink_type_ids: set[int] = set()

    def _build_drink_entities() -> list[NutriPointsDrinkSensor]:
        data = coordinator.data or {}
        rows_value = data.get("drink_totals")
        rows: list[Any] = rows_value if isinstance(rows_value, list) else []
        entities: list[NutriPointsDrinkSensor] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            drink_type_id = row.get("drink_type_id")
            if not isinstance(drink_type_id, int) or drink_type_id in known_drink_type_ids:
                continue
            known_drink_type_ids.add(drink_type_id)
            entities.append(NutriPointsDrinkSensor(coordinator=coordinator, drink_type_id=drink_type_id))
        return entities

    @callback
    def _async_discover_drink_entities() -> None:
        entities = _build_drink_entities()
        if entities:
            async_add_entities(entities)

    async_add_entities(
        [
            *(
                NutriPointsSensor(coordinator=coordinator, description=description)
                for description in SENSOR_DESCRIPTIONS
            ),
            NutriPointsWeightSensor(coordinator=coordinator),
            *_build_drink_entities(),
        ]
    )
    entry.async_on_unload(coordinator.async_add_listener(_async_discover_drink_entities))


class NutriPointsSensor(CoordinatorEntity[NutriPointsDataUpdateCoordinator], SensorEntity):
    entity_description: NutriSensorDescription

    def __init__(self, *, coordinator: NutriPointsDataUpdateCoordinator, description: NutriSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{description.key}"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return data.get(self.entity_description.source_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {
            "status": data.get("status"),
            "date": data.get("date"),
            "timezone": data.get("timezone"),
            "base_daily_points": data.get("base_daily_points"),
            "carryover_points": data.get("carryover_points"),
            "food_points": data.get("food_points"),
            "step_points": data.get("step_points"),
            "exercise_points": data.get("exercise_points"),
            "planned_points": data.get("planned_points"),
            "projected_remaining_points": data.get("projected_remaining_points"),
            "detail_message": data.get("detail_message"),
            "detail_error_code": data.get("detail_error_code"),
            "detail_retryable": data.get("detail_retryable"),
        }
        attrs.update(self.coordinator.connection_diagnostics())
        if self.coordinator.last_error:
            attrs[ATTR_LAST_ERROR] = self.coordinator.last_error
        return attrs

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.day_status_available)


class NutriPointsWeightSensor(CoordinatorEntity[NutriPointsDataUpdateCoordinator], SensorEntity):
    def __init__(self, *, coordinator: NutriPointsDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_weight"
        self._attr_name = "Nutri Current Weight"
        self._attr_icon = "mdi:scale-bathroom"
        self._attr_native_unit_of_measurement = "kg"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        weight_value = data.get("weight")
        weight: dict[str, Any] = weight_value if isinstance(weight_value, dict) else {}
        return weight.get("current_weight_kg")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        weight_value = data.get("weight")
        weight: dict[str, Any] = weight_value if isinstance(weight_value, dict) else {}
        attrs: dict[str, Any] = {
            "day_status": data.get("status"),
            "current_applies_to_date": weight.get("current_applies_to_date"),
            "start_weight_kg": weight.get("start_weight_kg"),
            "target_weight_kg": weight.get("target_weight_kg"),
            "weight_change_since_start_kg": weight.get("weight_change_since_start_kg"),
            "weight_lost_since_start_kg": weight.get("weight_lost_since_start_kg"),
            "distance_to_target_kg": weight.get("distance_to_target_kg"),
            "progress_percent": weight.get("progress_percent"),
            "direction": weight.get("direction"),
            "status": weight.get("status"),
            "previous_weight_kg": weight.get("previous_weight_kg"),
            "change_from_previous_kg": weight.get("change_from_previous_kg"),
            "detail_message": data.get("detail_message"),
            "detail_error_code": data.get("detail_error_code"),
            "detail_retryable": data.get("detail_retryable"),
        }
        attrs.update(self.coordinator.connection_diagnostics())
        if self.coordinator.last_weight_error:
            attrs[ATTR_LAST_ERROR] = self.coordinator.last_weight_error
        return attrs

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.weight_available)


class NutriPointsDrinkSensor(CoordinatorEntity[NutriPointsDataUpdateCoordinator], SensorEntity):
    def __init__(self, *, coordinator: NutriPointsDataUpdateCoordinator, drink_type_id: int) -> None:
        super().__init__(coordinator)
        self._drink_type_id = drink_type_id
        self._attr_unique_id = f"{DOMAIN}_drink_{drink_type_id}"
        self._attr_native_unit_of_measurement = "ml"
        self._attr_icon = "mdi:cup-water"

    def _current_row(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        rows_value = data.get("drink_totals")
        rows: list[Any] = rows_value if isinstance(rows_value, list) else []
        for row in rows:
            if isinstance(row, dict) and row.get("drink_type_id") == self._drink_type_id:
                return row
        return {}

    @property
    def name(self) -> str | None:
        row = self._current_row()
        drink_type_name = row.get("drink_type_name")
        if isinstance(drink_type_name, str) and drink_type_name.strip():
            return f"Nutri Drink {drink_type_name.strip()}"
        return f"Nutri Drink {self._drink_type_id}"

    @property
    def native_value(self):
        row = self._current_row()
        return row.get("total_volume_ml")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        row = self._current_row()
        attrs: dict[str, Any] = {
            "status": data.get("status"),
            "date": data.get("date"),
            "timezone": data.get("timezone"),
            "drink_type_id": row.get("drink_type_id"),
            "drink_type_name": row.get("drink_type_name"),
            "display_order": row.get("display_order"),
            "is_hidden_on_day": row.get("is_hidden_on_day"),
            "detail_message": data.get("detail_message"),
            "detail_error_code": data.get("detail_error_code"),
            "detail_retryable": data.get("detail_retryable"),
        }
        attrs.update(self.coordinator.connection_diagnostics())
        if self.coordinator.last_error:
            attrs[ATTR_LAST_ERROR] = self.coordinator.last_error
        return attrs

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.day_status_available)
