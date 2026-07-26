"""Test food weighing session validation and projections."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from custom_components.nutri_points.weighing_sessions import (
    NutriPointsWeighingSessionError,
    NutriPointsWeighingSessionManager,
    project_session,
    validate_session_snapshot,
)
from homeassistant.core import HomeAssistant


@pytest.fixture
def weighing_session() -> dict:
    """Return the published stable-rw-v7 weighing-session fixture."""
    return {
        "id": "7a99f071-37d8-4fe3-b1bd-09ac73190933",
        "status": "active",
        "food_item_id": 42,
        "food_name": "Scale oats",
        "nutrition_per_100g": {
            "basis_grams": 100,
            "protein_g": 12.5,
            "carbs_g": 60,
            "fat_g": 7,
            "fiber_g": 10,
        },
        "points_calculation": {
            "version": "food_points_macros_v1",
            "protein_coefficient": 16,
            "carbs_coefficient": 19,
            "fat_coefficient": 45,
            "fiber_coefficient": -14,
            "divisor": 175,
            "fiber_cap_g": 4,
            "macro_decimal_places": 4,
            "macro_rounding": "half_even",
            "rounding": "half_up",
            "minimum_points": 0,
        },
        "meal_type": "breakfast",
        "applies_to_date": "2026-07-25",
        "created_at": "2026-07-25T12:03:00Z",
        "expires_at": "2099-07-25T12:18:00Z",
        "terminal_at": None,
        "completed_food_log_id": None,
        "links": {
            "read": "/api/v1/weighing-sessions/session",
            "preview": "/api/v1/weighing-sessions/session/preview",
            "complete": "/api/v1/weighing-sessions/session/complete",
            "cancel": "/api/v1/weighing-sessions/session/cancel",
        },
    }


def test_v7_projection_vector(weighing_session: dict) -> None:
    """The local calculator matches the published 40 gram v7 vector."""
    result = project_session(validate_session_snapshot(weighing_session), 40)

    assert result == {
        "session_id": "7a99f071-37d8-4fe3-b1bd-09ac73190933",
        "calculation_version": "food_points_macros_v1",
        "grams": 40.0,
        "protein_g": 5.0,
        "carbs_g": 24.0,
        "fat_g": 2.8,
        "fiber_g": 4.0,
        "points": 3,
        "authoritative": False,
    }


@pytest.mark.parametrize("grams", [-1, 100001])
def test_projection_rejects_invalid_weight(weighing_session: dict, grams: float) -> None:
    """Projection weights remain inside the contract bounds."""
    with pytest.raises(NutriPointsWeighingSessionError, match="between"):
        project_session(validate_session_snapshot(weighing_session), grams)


def test_projection_rejects_unknown_version(weighing_session: dict) -> None:
    """Unknown calculation descriptors are never approximated."""
    snapshot = deepcopy(weighing_session)
    snapshot["points_calculation"]["version"] = "future_points_v2"

    with pytest.raises(NutriPointsWeighingSessionError, match="Unsupported"):
        project_session(validate_session_snapshot(snapshot), 40)


def test_projection_rounding_and_descriptor_rules(weighing_session: dict) -> None:
    """Macro rounding, fiber capping, points rounding, and the floor follow the descriptor."""
    snapshot = deepcopy(weighing_session)
    nutrition = snapshot["nutrition_per_100g"]
    calculation = snapshot["points_calculation"]
    nutrition.update(
        {
            "protein_g": 1.23445,
            "carbs_g": 1.23455,
            "fat_g": 0,
            "fiber_g": 10,
        }
    )
    calculation.update(
        {
            "protein_coefficient": 175,
            "carbs_coefficient": 0,
            "fat_coefficient": 0,
            "fiber_coefficient": 175,
            "divisor": 175,
            "fiber_cap_g": 4,
            "minimum_points": 6,
        }
    )

    result = project_session(validate_session_snapshot(snapshot), 100)

    assert result["protein_g"] == 1.2344
    assert result["carbs_g"] == 1.2346
    assert result["fiber_g"] == 10
    assert result["points"] == 6


def test_projection_uses_half_up_for_points(weighing_session: dict) -> None:
    """A positive half point rounds away from zero."""
    snapshot = deepcopy(weighing_session)
    snapshot["nutrition_per_100g"].update(
        {
            "protein_g": 2.5,
            "carbs_g": 0,
            "fat_g": 0,
            "fiber_g": 0,
        }
    )
    snapshot["points_calculation"].update(
        {
            "protein_coefficient": 175,
            "carbs_coefficient": 0,
            "fat_coefficient": 0,
            "fiber_coefficient": 0,
            "divisor": 175,
        }
    )

    assert project_session(validate_session_snapshot(snapshot), 100)["points"] == 3


def test_validation_preserves_trigger_payload(weighing_session: dict) -> None:
    """Validation preserves the complete nested payload for device automations."""
    assert validate_session_snapshot(weighing_session) == weighing_session


async def test_manager_persists_and_restores_session(
    hass: HomeAssistant,
    weighing_session: dict,
) -> None:
    """A retained immutable snapshot survives manager recreation."""
    api_client = AsyncMock()
    manager = NutriPointsWeighingSessionManager(hass, "entry-one", api_client)
    await manager.async_handle_started(weighing_session)

    restored = NutriPointsWeighingSessionManager(hass, "entry-one", api_client)
    api_client.async_get_weighing_session.return_value = weighing_session
    await restored.async_initialize(refresh=True)

    assert restored.project(weighing_session["id"], 40)["points"] == 3
    api_client.async_get_weighing_session.assert_awaited_once_with(weighing_session["id"])
