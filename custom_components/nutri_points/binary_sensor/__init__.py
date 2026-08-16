from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from custom_components.nutri_points.const import (
    ATTR_LAST_ERROR,
    CONF_LOW_POINTS_THRESHOLD,
    DEFAULT_LOW_POINTS_THRESHOLD,
)
from custom_components.nutri_points.coordinator import NutriPointsDataUpdateCoordinator
from custom_components.nutri_points.data import NutriPointsConfigEntry
from custom_components.nutri_points.entity import NutriPointsEntity
from custom_components.nutri_points.utils import entity_unique_id
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


@dataclass(frozen=True, kw_only=True)
class NutriBinarySensorDescription(BinarySensorEntityDescription):
    evaluator: Callable[[dict[str, Any], int], bool]


def _to_number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except TypeError, ValueError:
        return None


def _is_points_low(data: dict[str, Any], low_threshold: int) -> bool:
    remaining = _to_number(data.get("remaining_points"))
    return remaining is not None and remaining <= low_threshold


def _is_over_budget(data: dict[str, Any], _low_threshold: int) -> bool:
    remaining = _to_number(data.get("remaining_points"))
    return remaining is not None and remaining < 0


def _weigh_in_payload(data: dict[str, Any]) -> dict[str, Any]:
    readiness_value = data.get("readiness")
    readiness: dict[str, Any] = readiness_value if isinstance(readiness_value, dict) else {}
    weigh_in = readiness.get("weigh_in")
    return weigh_in if isinstance(weigh_in, dict) else {}


BINARY_SENSOR_DESCRIPTIONS: tuple[NutriBinarySensorDescription, ...] = (
    NutriBinarySensorDescription(
        key="points_low",
        translation_key="points_low",
        icon="mdi:alert-circle-outline",
        device_class=BinarySensorDeviceClass.PROBLEM,
        evaluator=_is_points_low,
    ),
    NutriBinarySensorDescription(
        key="over_budget",
        translation_key="over_budget",
        icon="mdi:alert-circle",
        device_class=BinarySensorDeviceClass.PROBLEM,
        evaluator=_is_over_budget,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NutriPointsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    low_points_threshold = int(
        entry.options.get(
            CONF_LOW_POINTS_THRESHOLD,
            entry.data.get(CONF_LOW_POINTS_THRESHOLD, DEFAULT_LOW_POINTS_THRESHOLD),
        )
    )
    async_add_entities(
        [
            *(
                NutriPointsBinarySensor(
                    coordinator=coordinator,
                    entry=entry,
                    description=description,
                    low_points_threshold=low_points_threshold,
                )
                for description in BINARY_SENSOR_DESCRIPTIONS
            ),
            NutriPointsWeighInDueBinarySensor(coordinator=coordinator, entry=entry),
        ]
    )


class NutriPointsBinarySensor(BinarySensorEntity, NutriPointsEntity):
    entity_description: NutriBinarySensorDescription

    def __init__(
        self,
        *,
        coordinator: NutriPointsDataUpdateCoordinator,
        entry: NutriPointsConfigEntry,
        description: NutriBinarySensorDescription,
        low_points_threshold: int,
    ) -> None:
        super().__init__(coordinator=coordinator, entry=entry)
        self.entity_description = description
        self._low_points_threshold = low_points_threshold
        self._attr_unique_id = entity_unique_id(entry, description.key)

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        return self.entity_description.evaluator(data, self._low_points_threshold)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {
            "status": data.get("status"),
            "date": data.get("date"),
            "timezone": data.get("timezone"),
            "remaining_points": data.get("remaining_points"),
            "food_points": data.get("food_points"),
            "activity_points": data.get("activity_points"),
            "low_points_threshold": self._low_points_threshold,
        }
        if self.coordinator.last_error:
            attrs[ATTR_LAST_ERROR] = self.coordinator.last_error
        return attrs

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.day_status_available)


class NutriPointsWeighInDueBinarySensor(BinarySensorEntity, NutriPointsEntity):
    def __init__(
        self,
        *,
        coordinator: NutriPointsDataUpdateCoordinator,
        entry: NutriPointsConfigEntry,
    ) -> None:
        super().__init__(coordinator=coordinator, entry=entry)
        self._attr_unique_id = entity_unique_id(entry, "weigh_in_due")
        self._attr_translation_key = "weigh_in_due"
        self._attr_icon = "mdi:scale-bathroom"
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        weigh_in = _weigh_in_payload(data)
        return weigh_in.get("status") in {"missing", "due"}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        weigh_in = _weigh_in_payload(data)
        attrs: dict[str, Any] = {
            "day_status": data.get("status"),
            "weigh_in_status": weigh_in.get("status"),
            "preferred_weigh_in_weekday": weigh_in.get("preferred_weigh_in_weekday"),
            "last_weigh_in_date": weigh_in.get("last_weigh_in_date"),
            "expected_weigh_in_date": weigh_in.get("expected_weigh_in_date"),
        }
        if self.coordinator.last_readiness_error:
            attrs[ATTR_LAST_ERROR] = self.coordinator.last_readiness_error
        return attrs

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.readiness_available)
