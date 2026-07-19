from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from custom_components.nutri_points.api import NutriPointsApiClient, NutriPointsApiError
from custom_components.nutri_points.const import DOMAIN
from custom_components.nutri_points.repairs import NutriPointsRuntimeIssueTracker
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)


class NutriPointsDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        *,
        api_client: NutriPointsApiClient,
        poll_interval_seconds: int,
        entry_id: str,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval_seconds),
        )
        self.api_client = api_client
        self.last_error: str | None = None
        self.last_weight_error: str | None = None
        self.last_readiness_error: str | None = None
        self.stream_status = "connecting"
        self.last_stream_error: str | None = None
        self.last_stream_event_at: str | None = None
        self.last_stream_connect_attempt_at: str | None = None
        self.last_stream_connected_at: str | None = None
        self.last_successful_poll_at: str | None = None
        self.day_status_available = False
        self.weight_available = False
        self.readiness_available = False
        self.runtime_issues = NutriPointsRuntimeIssueTracker(hass=hass, entry_id=entry_id)

    def _utc_now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def mark_stream_connecting(self) -> None:
        self.stream_status = "connecting"
        self.last_stream_connect_attempt_at = self._utc_now_iso()

    def mark_stream_connected(self) -> None:
        timestamp = self._utc_now_iso()
        self.stream_status = "connected"
        self.last_stream_error = None
        self.last_stream_connected_at = timestamp

    def mark_stream_event(self) -> None:
        self.last_stream_event_at = self._utc_now_iso()

    def mark_stream_backoff(self, error: str) -> None:
        self.stream_status = "backoff"
        self.last_stream_error = error

    def mark_stream_stopped(self) -> None:
        self.stream_status = "stopped"

    def connection_diagnostics(self) -> dict[str, Any]:
        diagnostics = {
            "connection_mode": "streaming" if self.stream_status == "connected" else "polling_fallback",
            "stream_status": self.stream_status,
            "last_stream_error": self.last_stream_error,
            "last_stream_event_at": self.last_stream_event_at,
            "last_stream_connect_attempt_at": self.last_stream_connect_attempt_at,
            "last_stream_connected_at": self.last_stream_connected_at,
            "last_successful_poll_at": self.last_successful_poll_at,
            "day_status_available": self.day_status_available,
            "weight_available": self.weight_available,
            "readiness_available": self.readiness_available,
        }
        diagnostics.update(self.runtime_issues.diagnostics())
        return diagnostics

    def record_runtime_failure(self, exc: Exception) -> None:
        self.runtime_issues.record_failure(exc)

    def record_runtime_success(self) -> None:
        self.runtime_issues.record_success()

    def _extract_weight_payload(self, overview: dict[str, Any]) -> dict[str, Any]:
        summary_value = overview.get("summary")
        summary: dict[str, Any] = summary_value if isinstance(summary_value, dict) else {}
        progress_value = overview.get("target_progress")
        target_progress: dict[str, Any] | None = progress_value if isinstance(progress_value, dict) else None
        current_weight = summary.get("current_weight_kg")
        start_weight = target_progress.get("start_weight_kg") if target_progress else None
        direction = target_progress.get("direction") if target_progress else None
        weight_change_since_start = None
        weight_lost_since_start = None
        if isinstance(current_weight, (int, float)) and isinstance(start_weight, (int, float)):
            weight_change_since_start = round(float(current_weight) - float(start_weight), 1)
            if direction == "lose":
                weight_lost_since_start = round(max(float(start_weight) - float(current_weight), 0.0), 1)
        return {
            "current_weight_kg": current_weight,
            "current_applies_to_date": summary.get("current_applies_to_date"),
            "previous_weight_kg": summary.get("previous_weight_kg"),
            "change_from_previous_kg": summary.get("change_from_previous_kg"),
            "start_weight_kg": start_weight,
            "target_weight_kg": target_progress.get("target_weight_kg") if target_progress else None,
            "weight_change_since_start_kg": weight_change_since_start,
            "weight_lost_since_start_kg": weight_lost_since_start,
            "distance_to_target_kg": target_progress.get("distance_to_target_kg") if target_progress else None,
            "progress_percent": target_progress.get("progress_percent") if target_progress else None,
            "direction": direction,
            "status": target_progress.get("status") if target_progress else None,
        }

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            self.last_error = None
            data = await self.api_client.async_get_today_status()
            self.last_successful_poll_at = self._utc_now_iso()
            self.day_status_available = True
            self.record_runtime_success()
        except NutriPointsApiError as exc:
            self.last_error = str(exc)
            self.day_status_available = False
            self.weight_available = False
            self.readiness_available = False
            self.record_runtime_failure(exc)
            raise UpdateFailed(str(exc)) from exc
        try:
            self.last_weight_error = None
            overview = await self.api_client.async_get_weight_overview(range="all")
            data["weight"] = self._extract_weight_payload(overview)
            self.weight_available = True
        except NutriPointsApiError as exc:
            self.last_weight_error = str(exc)
            data["weight"] = {}
            self.weight_available = False
        try:
            self.last_readiness_error = None
            data["readiness"] = await self.api_client.async_get_today_readiness()
            self.readiness_available = True
        except NutriPointsApiError as exc:
            self.last_readiness_error = str(exc)
            data["readiness"] = {}
            self.readiness_available = False
        return data
