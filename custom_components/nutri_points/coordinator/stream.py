from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import contextlib
import logging
import random
from typing import TYPE_CHECKING

from custom_components.nutri_points.api import NutriPointsApiClient, NutriPointsApiError
from custom_components.nutri_points.const import (
    SSE_RECONNECT_JITTER_SECONDS,
    SSE_RECONNECT_MAX_SECONDS,
    SSE_RECONNECT_MIN_SECONDS,
)

if TYPE_CHECKING:
    from .base import NutriPointsDataUpdateCoordinator

REFRESH_EVENT_NAMES = {
    "day_status_changed",
    "pending_weight_recap_changed",
    "readiness_changed",
    "weight_overview_changed",
}


class NutriPointsEventStreamListener:
    def __init__(
        self,
        *,
        api_client: NutriPointsApiClient,
        coordinator: NutriPointsDataUpdateCoordinator,
        on_day_status_changed: Callable[[], Awaitable[None]],
        logger: logging.Logger,
    ) -> None:
        self._api_client = api_client
        self._coordinator = coordinator
        self._on_day_status_changed = on_day_status_changed
        self._logger = logger
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._last_logged_error: str | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="nutri_points_sse_listener")

    async def stop(self) -> None:
        self._stop_event.set()
        self._coordinator.mark_stream_stopped()
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _handle_stream_connected(self) -> None:
        self._coordinator.mark_stream_connected()
        self._coordinator.record_runtime_success()
        self._last_logged_error = None
        try:
            await self._on_day_status_changed()
        except Exception as exc:  # pragma: no cover - coordinator refresh safety
            self._logger.warning("Nutri Points immediate refresh after SSE connect failed: %s", exc)

    async def _run(self) -> None:
        backoff_seconds = SSE_RECONNECT_MIN_SECONDS
        while not self._stop_event.is_set():
            self._coordinator.mark_stream_connecting()
            try:
                async for event_name, _payload in self._api_client.async_stream_home_assistant_events(
                    on_connect=self._handle_stream_connected
                ):
                    if self._stop_event.is_set():
                        break
                    backoff_seconds = SSE_RECONNECT_MIN_SECONDS
                    if event_name in REFRESH_EVENT_NAMES:
                        self._coordinator.mark_stream_event()
                        try:
                            await self._on_day_status_changed()
                        except Exception as exc:  # pragma: no cover - coordinator refresh safety
                            self._logger.warning("Nutri Points refresh after SSE event failed: %s", exc)
            except asyncio.CancelledError:
                raise
            except NutriPointsApiError as exc:
                error_message = str(exc)
                self._coordinator.mark_stream_backoff(error_message)
                self._coordinator.record_runtime_failure(exc)
                if error_message != self._last_logged_error:
                    self._logger.warning(
                        "Nutri Points SSE disconnected; falling back to polling until reconnect: %s",
                        exc,
                    )
                    self._last_logged_error = error_message
            except Exception as exc:  # pragma: no cover - safety catch
                self._coordinator.mark_stream_backoff(str(exc))
                self._coordinator.record_runtime_failure(exc)
                self._logger.exception("Unexpected Nutri Points SSE listener error")

            delay = min(SSE_RECONNECT_MAX_SECONDS, backoff_seconds)
            jitter = random.uniform(0.0, SSE_RECONNECT_JITTER_SECONDS)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay + jitter)
            backoff_seconds = min(SSE_RECONNECT_MAX_SECONDS, backoff_seconds * 2)
