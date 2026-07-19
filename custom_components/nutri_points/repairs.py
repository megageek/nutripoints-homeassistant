from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .api import (
    NutriPointsApiError,
    NutriPointsAuthError,
    NutriPointsContractError,
    NutriPointsHttpApiKeyForbiddenError,
    NutriPointsInvalidHostError,
)
from .const import (
    DOMAIN,
    RUNTIME_FAILURE_HTTP_API_KEY_FORBIDDEN,
    RUNTIME_FAILURE_INCOMPATIBLE_CONTRACT,
    RUNTIME_FAILURE_INVALID_AUTH,
    RUNTIME_FAILURE_INVALID_HOST,
    RUNTIME_FAILURE_TRANSIENT_TRANSPORT,
    TRANSIENT_RUNTIME_ISSUE_THRESHOLD,
)


def classify_runtime_failure(exc: Exception) -> str:
    if isinstance(exc, NutriPointsAuthError):
        return RUNTIME_FAILURE_INVALID_AUTH
    if isinstance(exc, NutriPointsInvalidHostError):
        return RUNTIME_FAILURE_INVALID_HOST
    if isinstance(exc, NutriPointsHttpApiKeyForbiddenError):
        return RUNTIME_FAILURE_HTTP_API_KEY_FORBIDDEN
    if isinstance(exc, NutriPointsContractError):
        return RUNTIME_FAILURE_INCOMPATIBLE_CONTRACT
    if isinstance(exc, NutriPointsApiError):
        return RUNTIME_FAILURE_TRANSIENT_TRANSPORT
    return RUNTIME_FAILURE_TRANSIENT_TRANSPORT


class NutriPointsRuntimeIssueTracker:
    def __init__(self, *, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self.failure_class: str | None = None
        self.failure_count = 0
        self.first_failure_at: str | None = None
        self.active_issue_id: str | None = None

    def _utc_now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def _issue_id(self, failure_class: str) -> str:
        return f"{self._entry_id}_{failure_class}"

    def diagnostics(self) -> dict[str, object]:
        return {
            "runtime_failure_class": self.failure_class,
            "runtime_failure_count": self.failure_count,
            "runtime_issue_active": self.active_issue_id is not None,
            "runtime_first_failure_at": self.first_failure_at,
        }

    def record_failure(self, exc: Exception) -> None:
        failure_class = classify_runtime_failure(exc)
        if failure_class == self.failure_class:
            self.failure_count += 1
        else:
            self.failure_class = failure_class
            self.failure_count = 1
            self.first_failure_at = self._utc_now_iso()

        should_raise = (
            failure_class != RUNTIME_FAILURE_TRANSIENT_TRANSPORT
            or self.failure_count >= TRANSIENT_RUNTIME_ISSUE_THRESHOLD
        )
        if should_raise:
            self._create_or_replace_issue(failure_class)

    def record_success(self) -> None:
        self.failure_class = None
        self.failure_count = 0
        self.first_failure_at = None
        if self.active_issue_id is not None:
            ir.async_delete_issue(self._hass, DOMAIN, self.active_issue_id)
            self.active_issue_id = None

    def _create_or_replace_issue(self, failure_class: str) -> None:
        issue_id = self._issue_id(failure_class)
        if self.active_issue_id == issue_id:
            return
        if self.active_issue_id is not None:
            ir.async_delete_issue(self._hass, DOMAIN, self.active_issue_id)
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id,
            is_fixable=failure_class != RUNTIME_FAILURE_TRANSIENT_TRANSPORT,
            severity=ir.IssueSeverity.WARNING
            if failure_class == RUNTIME_FAILURE_TRANSIENT_TRANSPORT
            else ir.IssueSeverity.ERROR,
            translation_key=f"runtime_{failure_class}",
        )
        self.active_issue_id = issue_id
