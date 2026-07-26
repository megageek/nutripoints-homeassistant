"""Runtime data types for Nutri Points config entries."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .api import NutriPointsApiClient, NutriPointsRuntimeMetadata
from .coordinator import NutriPointsDataUpdateCoordinator, NutriPointsEventStreamListener
from .weighing_sessions import NutriPointsWeighingSessionManager


@dataclass(slots=True)
class NutriPointsRuntimeData:
    """Runtime objects owned by one Nutri Points config entry."""

    api_client: NutriPointsApiClient
    coordinator: NutriPointsDataUpdateCoordinator
    listener: NutriPointsEventStreamListener
    automation_events_supported: bool
    weighing_sessions_supported: bool
    weighing_sessions: NutriPointsWeighingSessionManager
    runtime_metadata: NutriPointsRuntimeMetadata


type NutriPointsConfigEntry = ConfigEntry[NutriPointsRuntimeData]
