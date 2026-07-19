"""Test the client against every published Nutri Points contract generation."""

from __future__ import annotations

from typing import Any, Self

from nutripoints_api_contract import available_generations, load_json
import pytest

from custom_components.nutri_points.api import NutriPointsApiClient, NutriPointsContractError


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

    assert await client.async_validate_runtime() == fixtures["runtime"]


async def test_client_rejects_unknown_contract_generation() -> None:
    """Unknown contract generations fail before entity setup."""
    session = FakeSession(FakeResponse({"api_contract_version": "2099-01-01.stable-rw-v99"}))
    client = NutriPointsApiClient(session=session, base_url="http://nutri.local", api_key="npk_test")

    with pytest.raises(NutriPointsContractError, match="incompatible"):
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
