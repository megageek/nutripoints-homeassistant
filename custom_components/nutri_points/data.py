"""Runtime data types for Nutri Points config entries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .api import NutriPointsApiClient
from .coordinator import NutriPointsDataUpdateCoordinator, NutriPointsEventStreamListener


@dataclass(slots=True)
class NutriPointsRuntimeData:
    """Runtime objects owned by one Nutri Points config entry."""

    api_client: NutriPointsApiClient
    coordinator: NutriPointsDataUpdateCoordinator
    listener: NutriPointsEventStreamListener
    automation_events_supported: bool
    runtime_metadata: dict[str, Any]


type NutriPointsConfigEntry = ConfigEntry[NutriPointsRuntimeData]
