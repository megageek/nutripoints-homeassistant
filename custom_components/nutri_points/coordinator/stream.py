from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import contextlib
import logging
import random
from typing import TYPE_CHECKING, Any

from custom_components.nutri_points.api import NutriPointsApiClient, NutriPointsApiError, NutriPointsReplayGapError
from custom_components.nutri_points.const import (
    AUTOMATION_EVENT_NAMES,
    DOMAIN,
    SSE_RECONNECT_JITTER_SECONDS,
    SSE_RECONNECT_MAX_SECONDS,
    SSE_RECONNECT_MIN_SECONDS,
    automation_event_signal,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

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
        hass: Any | None = None,
        entry_id: str | None = None,
    ) -> None:
        self._api_client = api_client
        self._coordinator = coordinator
        self._on_day_status_changed = on_day_status_changed
        self._logger = logger
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._last_logged_error: str | None = None
        self._hass = hass
        self._entry_id = entry_id
        self._cursor: int | None = None
        self._cursor_store = Store(hass, 1, f"{DOMAIN}.{entry_id}.automation_cursor") if hass and entry_id else None

    async def _load_cursor(self) -> None:
        if self._cursor_store is None:
            return
        saved = await self._cursor_store.async_load()
        cursor = saved.get("last_event_id") if isinstance(saved, dict) else None
        self._cursor = cursor if isinstance(cursor, int) and cursor >= 0 else None

    async def _save_cursor(self, cursor: int) -> None:
        self._cursor = cursor
        if self._cursor_store is not None:
            await self._cursor_store.async_save({"last_event_id": cursor})

    def _clear_replay_gap_issue(self) -> None:
        if self._hass is not None and self._entry_id is not None:
            ir.async_delete_issue(self._hass, DOMAIN, f"{self._entry_id}_automation_replay_gap")

    def _create_replay_gap_issue(self) -> None:
        if self._hass is None or self._entry_id is None:
            return
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            f"{self._entry_id}_automation_replay_gap",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="automation_replay_gap",
        )

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
        self._clear_replay_gap_issue()
        try:
            await self._on_day_status_changed()
        except Exception as exc:  # pragma: no cover - coordinator refresh safety
            self._logger.warning("Nutri Points immediate refresh after SSE connect failed: %s", exc)

    async def _run(self) -> None:
        await self._load_cursor()
        backoff_seconds = SSE_RECONNECT_MIN_SECONDS
        while not self._stop_event.is_set():
            self._coordinator.mark_stream_connecting()
            try:
                async for event_id, event_name, payload in self._api_client.async_stream_home_assistant_events(
                    on_connect=self._handle_stream_connected,
                    last_event_id=self._cursor,
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
                    if event_name in AUTOMATION_EVENT_NAMES and self._hass is not None and self._entry_id is not None:
                        async_dispatcher_send(self._hass, automation_event_signal(self._entry_id), event_name, payload)
                    if event_id is not None:
                        try:
                            await self._save_cursor(int(event_id))
                        except ValueError:
                            self._logger.warning("Nutri Points SSE returned an invalid event id: %s", event_id)
            except asyncio.CancelledError:
                raise
            except NutriPointsReplayGapError as exc:
                if exc.latest_event_id is not None:
                    await self._save_cursor(exc.latest_event_id)
                self._create_replay_gap_issue()
                self._coordinator.mark_stream_backoff(str(exc))
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
