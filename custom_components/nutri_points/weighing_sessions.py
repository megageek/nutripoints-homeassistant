"""Food weighing session persistence and local projections."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, ReadOnly, TypedDict, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import NutriPointsApiClient
from .const import DOMAIN

CALCULATION_VERSION = "food_points_macros_v1"
ACTIVE_STATUS = "active"
TERMINAL_STATUSES = {"cancelled", "completed", "expired"}


class NutriPointsNutritionSnapshot(TypedDict):
    """Immutable per-basis nutrition values from the server contract."""

    basis_grams: ReadOnly[int]
    protein_g: ReadOnly[float]
    carbs_g: ReadOnly[float]
    fat_g: ReadOnly[float]
    fiber_g: ReadOnly[float]


class NutriPointsCalculationDescriptor(TypedDict):
    """Versioned immutable points calculation parameters."""

    version: ReadOnly[str]
    protein_coefficient: ReadOnly[int]
    carbs_coefficient: ReadOnly[int]
    fat_coefficient: ReadOnly[int]
    fiber_coefficient: ReadOnly[int]
    divisor: ReadOnly[int]
    fiber_cap_g: ReadOnly[int]
    macro_decimal_places: ReadOnly[int]
    macro_rounding: ReadOnly[str]
    rounding: ReadOnly[str]
    minimum_points: ReadOnly[int]


class NutriPointsProjectionResult(TypedDict):
    """Common local or authoritative calculation response."""

    session_id: str
    calculation_version: str
    grams: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    points: int
    authoritative: bool


class NutriPointsWeighingSessionSnapshot(TypedDict):
    """Validated session snapshot with immutable calculation inputs."""

    id: ReadOnly[str]
    status: str
    food_item_id: ReadOnly[int | None]
    food_name: ReadOnly[str]
    nutrition_per_100g: ReadOnly[NutriPointsNutritionSnapshot]
    points_calculation: ReadOnly[NutriPointsCalculationDescriptor]
    meal_type: ReadOnly[str | None]
    applies_to_date: ReadOnly[str]
    created_at: ReadOnly[str]
    expires_at: ReadOnly[str]
    terminal_at: str | None
    completed_food_log_id: int | None
    links: ReadOnly[dict[str, str]]


class NutriPointsWeighingSessionError(ValueError):
    """Raised when locally retained weighing-session data is unusable."""


def _number(value: object, field: str) -> Decimal:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise NutriPointsWeighingSessionError(f"Session field '{field}' must be numeric.")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise NutriPointsWeighingSessionError(f"Session field '{field}' is invalid.") from exc
    if not result.is_finite():
        raise NutriPointsWeighingSessionError(f"Session field '{field}' must be finite.")
    return result


def validate_session_snapshot(payload: dict[str, Any]) -> NutriPointsWeighingSessionSnapshot:
    """Validate a v7 session snapshot while preserving its wire representation."""
    required_strings = ("id", "status", "food_name", "applies_to_date", "created_at", "expires_at")
    for field in required_strings:
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise NutriPointsWeighingSessionError(f"Session field '{field}' is missing.")
    if payload["status"] not in {ACTIVE_STATUS, *TERMINAL_STATUSES}:
        raise NutriPointsWeighingSessionError("Session status is invalid.")
    if dt_util.parse_datetime(payload["expires_at"]) is None:
        raise NutriPointsWeighingSessionError("Session expiry is invalid.")
    nutrition = payload.get("nutrition_per_100g")
    calculation = payload.get("points_calculation")
    links = payload.get("links")
    if not isinstance(nutrition, dict) or not isinstance(calculation, dict) or not isinstance(links, dict):
        raise NutriPointsWeighingSessionError("Session nutrition, calculation, or links are missing.")
    for field in ("protein_g", "carbs_g", "fat_g", "fiber_g"):
        if _number(nutrition.get(field), f"nutrition_per_100g.{field}") < 0:
            raise NutriPointsWeighingSessionError(f"Session field 'nutrition_per_100g.{field}' cannot be negative.")
    _number(nutrition.get("basis_grams", 100), "nutrition_per_100g.basis_grams")
    if not isinstance(calculation.get("version"), str):
        raise NutriPointsWeighingSessionError("Session calculation version is missing.")
    for field in (
        "protein_coefficient",
        "carbs_coefficient",
        "fat_coefficient",
        "fiber_coefficient",
        "divisor",
        "fiber_cap_g",
        "macro_decimal_places",
        "minimum_points",
    ):
        _number(calculation.get(field), f"points_calculation.{field}")
    for field in ("macro_rounding", "rounding"):
        if not isinstance(calculation.get(field), str):
            raise NutriPointsWeighingSessionError(f"Session field 'points_calculation.{field}' is missing.")
    if _number(nutrition.get("basis_grams", 100), "nutrition_per_100g.basis_grams") <= 0:
        raise NutriPointsWeighingSessionError("Session basis grams must be positive.")
    if _number(calculation["divisor"], "points_calculation.divisor") <= 0:
        raise NutriPointsWeighingSessionError("Session points divisor must be positive.")
    if _number(calculation["fiber_cap_g"], "points_calculation.fiber_cap_g") < 0:
        raise NutriPointsWeighingSessionError("Session fiber cap cannot be negative.")
    places = _number(calculation["macro_decimal_places"], "points_calculation.macro_decimal_places")
    if places != places.to_integral_value() or not 0 <= places <= 8:
        raise NutriPointsWeighingSessionError("Session macro decimal places must be an integer from 0 through 8.")
    if _number(calculation["minimum_points"], "points_calculation.minimum_points") < 0:
        raise NutriPointsWeighingSessionError("Session minimum points cannot be negative.")
    return cast(NutriPointsWeighingSessionSnapshot, deepcopy(payload))


def validate_projection_result(payload: dict[str, Any], session_id: str) -> NutriPointsProjectionResult:
    """Validate and normalize an authoritative server preview."""
    if payload.get("session_id") != session_id:
        raise NutriPointsWeighingSessionError("Server preview returned a different session identifier.")
    if not isinstance(payload.get("calculation_version"), str):
        raise NutriPointsWeighingSessionError("Server preview omitted its calculation version.")
    if payload.get("authoritative", True) is not True:
        raise NutriPointsWeighingSessionError("Server preview was not authoritative.")
    values = {
        field: float(_number(payload.get(field), field))
        for field in ("grams", "protein_g", "carbs_g", "fat_g", "fiber_g")
    }
    points = payload.get("points")
    if not isinstance(points, int) or isinstance(points, bool) or points < 0:
        raise NutriPointsWeighingSessionError("Server preview returned invalid points.")
    return NutriPointsProjectionResult(
        session_id=session_id,
        calculation_version=payload["calculation_version"],
        **values,
        points=points,
        authoritative=True,
    )


def project_session(
    snapshot: NutriPointsWeighingSessionSnapshot,
    grams: float,
) -> NutriPointsProjectionResult:
    """Calculate an advisory projection from an immutable session snapshot."""
    weight = _number(grams, "grams")
    if weight < 0 or weight > 100000:
        raise NutriPointsWeighingSessionError("Grams must be between 0 and 100000.")
    calculation = snapshot["points_calculation"]
    if calculation["version"] != CALCULATION_VERSION:
        raise NutriPointsWeighingSessionError(f"Unsupported weighing calculation version '{calculation['version']}'.")
    if calculation["macro_rounding"] != "half_even" or calculation["rounding"] != "half_up":
        raise NutriPointsWeighingSessionError("Unsupported weighing-session rounding descriptor.")
    places = int(calculation["macro_decimal_places"])
    quantum = Decimal(1).scaleb(-places)
    nutrition = snapshot["nutrition_per_100g"]
    basis = _number(nutrition.get("basis_grams", 100), "basis_grams")
    if basis <= 0:
        raise NutriPointsWeighingSessionError("Session basis grams must be positive.")

    macros = {
        key: (_number(nutrition[key], key) * weight / basis).quantize(quantum, rounding=ROUND_HALF_EVEN)
        for key in ("protein_g", "carbs_g", "fat_g", "fiber_g")
    }
    scored_fiber = min(macros["fiber_g"], _number(calculation["fiber_cap_g"], "fiber_cap_g"))
    score = (
        macros["protein_g"] * _number(calculation["protein_coefficient"], "protein_coefficient")
        + macros["carbs_g"] * _number(calculation["carbs_coefficient"], "carbs_coefficient")
        + macros["fat_g"] * _number(calculation["fat_coefficient"], "fat_coefficient")
        + scored_fiber * _number(calculation["fiber_coefficient"], "fiber_coefficient")
    ) / _number(calculation["divisor"], "divisor")
    points = int(score.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    points = max(points, int(calculation["minimum_points"]))
    return NutriPointsProjectionResult(
        session_id=snapshot["id"],
        calculation_version=calculation["version"],
        grams=float(weight),
        protein_g=float(macros["protein_g"]),
        carbs_g=float(macros["carbs_g"]),
        fat_g=float(macros["fat_g"]),
        fiber_g=float(macros["fiber_g"]),
        points=points,
        authoritative=False,
    )


class NutriPointsWeighingSessionManager:
    """Own retained weighing sessions for one config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str, api_client: NutriPointsApiClient) -> None:
        self._hass = hass
        self._api_client = api_client
        self._store = Store[dict[str, Any]](hass, 1, f"{DOMAIN}.{entry_id}.weighing_sessions")
        self._sessions: dict[str, NutriPointsWeighingSessionSnapshot] = {}
        self.last_validation_error: str | None = None

    def _is_expired(self, session: NutriPointsWeighingSessionSnapshot) -> bool:
        expires_at = dt_util.parse_datetime(session["expires_at"])
        return expires_at is None or expires_at <= dt_util.utcnow()

    async def async_initialize(self, *, refresh: bool) -> None:
        """Restore persisted sessions and refresh active server state once."""
        saved = await self._store.async_load()
        rows = saved.get("sessions") if isinstance(saved, dict) else None
        if isinstance(rows, dict):
            for session_id, payload in rows.items():
                if not isinstance(session_id, str) or not isinstance(payload, dict):
                    continue
                try:
                    session = validate_session_snapshot(payload)
                except NutriPointsWeighingSessionError as exc:
                    self.last_validation_error = str(exc)
                    continue
                if not self._is_expired(session):
                    self._sessions[session_id] = session
        if refresh and self._sessions:
            results = await asyncio.gather(
                *(self._api_client.async_get_weighing_session(session_id) for session_id in self._sessions),
                return_exceptions=True,
            )
            for session_id, result in zip(tuple(self._sessions), results, strict=True):
                if isinstance(result, dict):
                    try:
                        self._sessions[session_id] = validate_session_snapshot(result)
                    except NutriPointsWeighingSessionError as exc:
                        self.last_validation_error = str(exc)
        await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save({"sessions": self._sessions})

    async def async_handle_started(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate and persist a newly started session."""
        try:
            session = validate_session_snapshot(payload)
        except NutriPointsWeighingSessionError as exc:
            self.last_validation_error = str(exc)
            raise
        self.last_validation_error = None
        self._sessions[session["id"]] = session
        await self._async_save()
        return dict(deepcopy(session))

    def session(self, session_id: str) -> NutriPointsWeighingSessionSnapshot:
        """Return an active retained session."""
        session = self._sessions.get(session_id)
        if session is None:
            raise NutriPointsWeighingSessionError(f"Weighing session '{session_id}' is not retained.")
        if self._is_expired(session):
            del self._sessions[session_id]
            self._hass.async_create_task(
                self._async_save(),
                f"remove expired Nutri Points weighing session {session_id}",
            )
            raise NutriPointsWeighingSessionError(f"Weighing session '{session_id}' has expired.")
        if session["status"] != ACTIVE_STATUS:
            raise NutriPointsWeighingSessionError(f"Weighing session '{session_id}' is {session['status']}.")
        return session

    def project(self, session_id: str, grams: float) -> NutriPointsProjectionResult:
        """Calculate a local projection."""
        return project_session(self.session(session_id), grams)

    async def async_preview(self, session_id: str, grams: float) -> dict[str, Any]:
        """Request an authoritative projection."""
        self.session(session_id)
        result = await self._api_client.async_preview_weighing_session(session_id, grams)
        return dict(validate_projection_result(result, session_id))

    async def async_complete(self, session_id: str, grams: float) -> dict[str, Any]:
        """Complete and persist the terminal session."""
        self.session(session_id)
        result = validate_session_snapshot(await self._api_client.async_complete_weighing_session(session_id, grams))
        self._sessions[session_id] = result
        await self._async_save()
        return dict(result)

    async def async_cancel(self, session_id: str) -> dict[str, Any]:
        """Cancel and persist the terminal session."""
        self.session(session_id)
        result = validate_session_snapshot(await self._api_client.async_cancel_weighing_session(session_id))
        self._sessions[session_id] = result
        await self._async_save()
        return dict(result)

    def diagnostics(self) -> dict[str, Any]:
        """Return privacy-safe session diagnostics."""
        return {
            "retained_sessions": [
                {
                    "session_id": session_id,
                    "status": session["status"],
                    "expires_at": session["expires_at"],
                    "calculation_version": session["points_calculation"]["version"],
                }
                for session_id, session in self._sessions.items()
            ],
            "last_validation_error": self.last_validation_error,
        }
