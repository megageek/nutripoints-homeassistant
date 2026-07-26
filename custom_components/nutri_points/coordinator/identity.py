"""Coordinate permanent server identity mismatch handling."""

from __future__ import annotations

from custom_components.nutri_points.api import NutriPointsIdentityMismatchError
from custom_components.nutri_points.repairs import async_create_identity_mismatch_issue
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class NutriPointsIdentityGuard:
    """Latch an identity mismatch and unload the affected config entry."""

    def __init__(self, *, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self.mismatch: NutriPointsIdentityMismatchError | None = None
        self._unload_requested = False

    async def async_handle_mismatch(self, exc: NutriPointsIdentityMismatchError) -> None:
        """Persist the mismatch and request one asynchronous unload."""
        if self.mismatch is None:
            self.mismatch = exc
            async_create_identity_mismatch_issue(
                self._hass,
                entry_id=self._entry.entry_id,
                expected_uuid=exc.expected_uuid,
                observed_uuid=exc.observed_uuid,
            )
        if self._unload_requested:
            return
        self._unload_requested = True
        self._hass.async_create_task(
            self._hass.config_entries.async_unload(self._entry.entry_id),
            "unload Nutri Points after server identity mismatch",
        )
