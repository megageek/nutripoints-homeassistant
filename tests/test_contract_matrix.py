"""Test the client against every published Nutri Points contract generation."""

from __future__ import annotations

from typing import Any, Self

from nutripoints_api_contract import available_generations, load_json
import pytest

from custom_components.nutri_points.api import (
    NutriPointsApiClient,
    NutriPointsAuthError,
    NutriPointsContractError,
    NutriPointsSessionError,
)
from custom_components.nutri_points.const import AUTOMATION_EVENT_NAMES, SUPPORTED_API_CONTRACT_TAGS


class FakeResponse:
    """Minimal aiohttp response context for client tests."""

    def __init__(self, payload: dict[str, Any], *, status: int = 200) -> None:
        self.content_type = "application/json"
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self._payload

    async def text(self) -> str:
        return ""


class FakeSession:
    """Record client requests and return one configured response."""

    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.response


@pytest.mark.parametrize("generation", available_generations())
async def test_client_accepts_each_published_generation(generation: str) -> None:
    """Every packaged generation remains inside the compatibility window."""
    fixtures = load_json(generation, "home_assistant/fixtures.json")
    session = FakeSession(FakeResponse(fixtures["runtime"]))
    client = NutriPointsApiClient(session=session, base_url="http://nutri.local", api_key="npk_test")

    expected = {**fixtures["runtime"], "server_uuid": fixtures["runtime"].get("server_uuid")}
    assert await client.async_validate_runtime() == expected


async def test_client_rejects_unknown_contract_generation() -> None:
    """Unknown contract generations fail before entity setup."""
    session = FakeSession(FakeResponse({"api_contract_version": "2099-01-01.stable-rw-v99"}))
    client = NutriPointsApiClient(session=session, base_url="http://nutri.local", api_key="npk_test")

    with pytest.raises(NutriPointsContractError, match="incompatible"):
        await client.async_validate_runtime()


def test_stable_rw_v9_profile_exposes_recipe_print_events() -> None:
    """The v9 compatibility profile and integration advertise recipe print requests."""
    profile = load_json("stable-rw-v9", "home_assistant/profile.json")

    assert "stable-rw-v9" in SUPPORTED_API_CONTRACT_TAGS
    assert "recipe_print_requested" in profile["sse_events"]
    assert "recipe_print_requested" in AUTOMATION_EVENT_NAMES


def test_stable_rw_v11_preserves_home_assistant_payload_contract() -> None:
    """V11 adds food-log provenance without changing Home Assistant payloads."""
    v10_profile = load_json("stable-rw-v10", "home_assistant/profile.json")
    v11_profile = load_json("stable-rw-v11", "home_assistant/profile.json")

    assert "stable-rw-v11" in SUPPORTED_API_CONTRACT_TAGS
    assert v11_profile == v10_profile


@pytest.mark.parametrize(
    "server_uuid",
    [
        None,
        "not-a-uuid",
        "8F13A050-CC4C-4F89-AAF8-5BADB51CBF5D",
        "8f13a050-cc4c-1f89-aaf8-5badb51cbf5d",
    ],
)
@pytest.mark.parametrize(
    "generation",
    [
        "stable-rw-v5",
        "stable-rw-v6",
        "stable-rw-v7",
        "stable-rw-v8",
        "stable-rw-v9",
        "stable-rw-v10",
        "stable-rw-v11",
    ],
)
async def test_identity_generations_reject_invalid_server_uuid(
    server_uuid: object,
    generation: str,
) -> None:
    """V5 and newer require a lowercase canonical UUIDv4 server identity."""
    session = FakeSession(
        FakeResponse(
            {
                "api_contract_version": f"2026-07-24.{generation}",
                "server_uuid": server_uuid,
            }
        )
    )
    client = NutriPointsApiClient(
        session=session,
        base_url="http://nutri.local",
        api_key="npk_test",
    )

    with pytest.raises(NutriPointsContractError, match="server_uuid"):
        await client.async_validate_runtime()


@pytest.mark.parametrize("generation", available_generations())
async def test_setup_blocked_normalizes_across_generations(generation: str) -> None:
    """Legacy 409 and current 200 setup-blocked payloads produce the same internal state."""
    fixture = load_json(generation, "home_assistant/fixtures.json")["setup_blocked"]
    session = FakeSession(FakeResponse(fixture["body"], status=fixture["http_status"]))
    client = NutriPointsApiClient(session=session, base_url="http://nutri.local", api_key="npk_test")

    result = await client.async_get_today_status()

    assert result["status"] == "setup_blocked"
    assert result["detail_error_code"] == "budget_not_ready"


@pytest.mark.parametrize("message", ["API key expired.", "API key revoked.", "User is disabled."])
async def test_v10_invalid_user_owned_credentials_are_auth_errors(message: str) -> None:
    """Invalid v10 user-owned credentials consistently request reauthentication."""
    session = FakeSession(FakeResponse({"detail": message}, status=401))
    client = NutriPointsApiClient(session=session, base_url="http://nutri.local", api_key="npk_test")

    with pytest.raises(NutriPointsAuthError, match="provided API key"):
        await client.async_get_today_status()


async def test_write_uses_bearer_and_retry_identifiers() -> None:
    """Writes preserve the public authentication and replay contract."""
    session = FakeSession(FakeResponse({"id": 12}, status=201))
    client = NutriPointsApiClient(session=session, base_url="http://nutri.local", api_key="npk_test")

    await client.async_log_activity(kcal=120, applies_to_date="2026-07-19", logged_at=None)

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/api/v1/logs/activity")
    assert call["headers"]["Authorization"] == "Bearer npk_test"
    assert call["headers"]["Idempotency-Key"] == call["headers"]["X-Client-Mutation-Id"]


async def test_weighing_session_client_methods() -> None:
    """Session operations use the published v7 paths and mutation identifiers."""
    session = FakeSession(FakeResponse({"id": "session-1"}))
    client = NutriPointsApiClient(session=session, base_url="http://nutri.local", api_key="npk_test")

    await client.async_get_weighing_session("session-1")
    await client.async_preview_weighing_session("session-1", 40)
    await client.async_complete_weighing_session("session-1", 40)
    await client.async_cancel_weighing_session("session-1")

    assert [(call["method"], call["url"].removeprefix("http://nutri.local")) for call in session.calls] == [
        ("GET", "/api/v1/weighing-sessions/session-1"),
        ("POST", "/api/v1/weighing-sessions/session-1/preview"),
        ("POST", "/api/v1/weighing-sessions/session-1/complete"),
        ("POST", "/api/v1/weighing-sessions/session-1/cancel"),
    ]
    assert "Idempotency-Key" not in session.calls[0]["headers"]
    assert all("Idempotency-Key" in call["headers"] for call in session.calls[1:])


async def test_weighing_session_stable_error_is_typed() -> None:
    """Published session error codes remain available to callers."""
    session = FakeSession(
        FakeResponse(
            {
                "detail": {
                    "error_code": "food_weighing_session_expired",
                    "message": "The weighing session expired.",
                }
            },
            status=409,
        )
    )
    client = NutriPointsApiClient(session=session, base_url="http://nutri.local", api_key="npk_test")

    with pytest.raises(NutriPointsSessionError) as caught:
        await client.async_preview_weighing_session("session-1", 40)

    assert caught.value.error_code == "food_weighing_session_expired"
