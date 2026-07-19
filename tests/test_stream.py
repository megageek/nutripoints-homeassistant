"""Test Nutri Points SSE refresh and recovery behavior."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock

from custom_components.nutri_points.api import NutriPointsApiError
from custom_components.nutri_points.coordinator import NutriPointsEventStreamListener


class FakeCoordinator:
    """Record stream lifecycle calls."""

    def __init__(self) -> None:
        self.connected = 0
        self.events = 0
        self.failures: list[str] = []
        self.stopped = 0

    def mark_stream_connecting(self) -> None:
        return None

    def mark_stream_connected(self) -> None:
        self.connected += 1

    def mark_stream_event(self) -> None:
        self.events += 1

    def mark_stream_backoff(self, _error: str) -> None:
        return None

    def mark_stream_stopped(self) -> None:
        self.stopped += 1

    def record_runtime_success(self) -> None:
        return None

    def record_runtime_failure(self, exc: Exception) -> None:
        self.failures.append(str(exc))


async def test_stream_refreshes_on_connect_and_known_events() -> None:
    """Connect and all documented trigger events request fresh coordinator data."""
    refreshed = asyncio.Event()
    refresh = AsyncMock()
    coordinator = FakeCoordinator()

    class Api:
        async def async_stream_home_assistant_events(self, *, on_connect=None, last_event_id=None):
            await on_connect()
            for event in ("readiness_changed", "weight_overview_changed", "unknown"):
                yield None, event, {}
            refreshed.set()

    listener = NutriPointsEventStreamListener(
        api_client=Api(),
        coordinator=coordinator,
        on_day_status_changed=refresh,
        logger=logging.getLogger(__name__),
    )
    listener.start()
    await asyncio.wait_for(refreshed.wait(), timeout=1)
    await listener.stop()

    assert refresh.await_count == 3
    assert coordinator.connected == 1
    assert coordinator.events == 2
    assert coordinator.stopped == 1


async def test_stream_records_api_failure_before_reconnect(monkeypatch) -> None:
    """Transport errors activate polling fallback before the next connection attempt."""
    monkeypatch.setattr("custom_components.nutri_points.coordinator.stream.SSE_RECONNECT_MIN_SECONDS", 0.0)
    monkeypatch.setattr("custom_components.nutri_points.coordinator.stream.SSE_RECONNECT_MAX_SECONDS", 0.0)
    monkeypatch.setattr("custom_components.nutri_points.coordinator.stream.SSE_RECONNECT_JITTER_SECONDS", 0.0)
    refreshed = asyncio.Event()
    coordinator = FakeCoordinator()

    class Api:
        calls = 0

        async def async_stream_home_assistant_events(self, *, on_connect=None, last_event_id=None):
            self.calls += 1
            if self.calls == 1:
                raise NutriPointsApiError("temporary")
            await on_connect()
            refreshed.set()
            if False:
                yield None, "day_status_changed", {}

    listener = NutriPointsEventStreamListener(
        api_client=Api(),
        coordinator=coordinator,
        on_day_status_changed=AsyncMock(),
        logger=logging.getLogger(__name__),
    )
    listener.start()
    await asyncio.wait_for(refreshed.wait(), timeout=1)
    await listener.stop()

    assert coordinator.failures == ["temporary"]
    assert coordinator.connected == 1
