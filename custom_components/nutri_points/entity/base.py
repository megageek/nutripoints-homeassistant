"""Base entity for Nutri Points platforms."""

from __future__ import annotations

from custom_components.nutri_points.const import CONF_BASE_URL, DOMAIN
from custom_components.nutri_points.coordinator import NutriPointsDataUpdateCoordinator
from custom_components.nutri_points.data import NutriPointsConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity


class NutriPointsEntity(CoordinatorEntity[NutriPointsDataUpdateCoordinator]):
    """Attach Nutri Points entities to their config entry and service device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        coordinator: NutriPointsDataUpdateCoordinator,
        entry: NutriPointsConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        runtime = entry.runtime_data.runtime_metadata
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Nutri Points",
            model="Nutri Points Server",
            configuration_url=entry.data[CONF_BASE_URL],
            sw_version=str(runtime.get("version")) if runtime.get("version") is not None else None,
        )
