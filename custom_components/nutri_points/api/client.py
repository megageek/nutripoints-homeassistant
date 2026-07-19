from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
import json
from typing import Any
from uuid import uuid4

from aiohttp import (
    ClientConnectorCertificateError,
    ClientConnectorError,
    ClientError,
    ClientResponseError,
    ClientSession,
    ClientSSLError,
)

from custom_components.nutri_points.const import (
    ACTIVITY_LOG_ENDPOINT,
    DRINK_LOG_ENDPOINT,
    DRINK_SETTINGS_ENDPOINT,
    FOOD_LOG_ENDPOINT,
    HA_EVENTS_ENDPOINT,
    READINESS_ENDPOINT,
    RUNTIME_ENDPOINT,
    STEPS_LOG_ENDPOINT,
    SUPPORTED_API_CONTRACT_TAGS,
    TODAY_ENDPOINT,
    WEIGHT_LOG_ENDPOINT,
    WEIGHT_OVERVIEW_ENDPOINT,
)


class NutriPointsApiError(Exception):
    """Base error for Nutri Points API failures."""


class NutriPointsAuthError(NutriPointsApiError):
    """Raised when auth fails."""


class NutriPointsContractError(NutriPointsApiError):
    """Raised when runtime contract is incompatible."""


class NutriPointsInvalidHostError(NutriPointsApiError):
    """Raised when the Nutri Points server rejects the request Host header."""


class NutriPointsHttpApiKeyForbiddenError(NutriPointsApiError):
    """Raised when HTTP API-key access is forbidden for the caller network."""


class NutriPointsTlsError(NutriPointsApiError):
    """Raised when TLS validation fails."""


class NutriPointsUnexpectedServerError(NutriPointsApiError):
    """Raised when the remote server is reachable but does not look like Nutri Points."""


def _normalize_today_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("status")
    if status == "setup_blocked":
        detail_value = payload.get("detail")
        detail: dict[str, Any] = detail_value if isinstance(detail_value, dict) else {}
        return {
            "status": "setup_blocked",
            "date": payload.get("date"),
            "timezone": payload.get("timezone"),
            "detail_message": detail.get("message"),
            "detail_error_code": detail.get("error_code"),
            "detail_retryable": detail.get("retryable"),
        }
    if status is None:
        normalized = dict(payload)
        normalized["status"] = "ready"
        return normalized
    return payload


class NutriPointsApiClient:
    def __init__(self, *, session: ClientSession, base_url: str, api_key: str, verify_ssl: bool = True) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._verify_ssl = verify_ssl

    def _headers(self, *, with_idempotency: bool) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if with_idempotency:
            key = str(uuid4())
            headers["Idempotency-Key"] = key
            headers["X-Client-Mutation-Id"] = key
        return headers

    async def _read_error_message(self, response: Any) -> str:
        message: str | None = None
        if response.content_type == "application/json":
            try:
                payload = await response.json()
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                detail = payload.get("detail")
                if isinstance(detail, str):
                    message = detail
                elif isinstance(detail, dict):
                    detail_message = detail.get("message")
                    if isinstance(detail_message, str):
                        message = detail_message
        if message:
            return message
        try:
            text = await response.text()
        except Exception:
            text = ""
        return text.strip() or f"HTTP {response.status}"

    async def _request(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        with_idempotency: bool = False,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(with_idempotency=with_idempotency),
                json=payload,
                ssl=self._verify_ssl,
            ) as response:
                if response.status == 401:
                    raise NutriPointsAuthError("Authentication failed with the provided API key.")
                if response.status >= 400:
                    await self._handle_error_response(response)
                if response.content_type == "application/json":
                    return await response.json()
                return {}
        except NutriPointsAuthError:
            raise
        except (ClientConnectorCertificateError, ClientSSLError) as exc:
            raise NutriPointsTlsError(
                "TLS verification failed while connecting to Nutri Points. Check the server certificate "
                "or disable TLS verification if appropriate."
            ) from exc
        except ClientConnectorError as exc:
            raise NutriPointsApiError(f"Unable to reach Nutri Points API: {exc}") from exc
        except ClientError as exc:
            raise NutriPointsApiError(f"Unable to reach Nutri Points API: {exc}") from exc

    async def _handle_error_response(self, response: Any) -> None:
        error_message = await self._read_error_message(response)
        normalized = error_message.lower()
        if response.status == 400 and "invalid host" in normalized:
            raise NutriPointsInvalidHostError(
                "Nutri Points rejected the Host header. Update TRUSTED_HOSTS to include this hostname or IP."
            )
        if response.status == 403 and "http api key access is not allowed" in normalized:
            raise NutriPointsHttpApiKeyForbiddenError(
                "HTTP API key access is blocked for this caller. Add the Home Assistant network "
                "to API_KEY_HTTP_ALLOWED_CIDRS."
            )
        raise NutriPointsApiError(f"Nutri Points API request failed: {response.status} {error_message}")

    async def async_validate_runtime(self) -> dict[str, Any]:
        runtime = await self._request(method="GET", path=RUNTIME_ENDPOINT)
        if not isinstance(runtime, dict) or "api_contract_version" not in runtime:
            raise NutriPointsUnexpectedServerError(
                "Connected server did not return Nutri Points runtime metadata from /api/v1/system/runtime."
            )
        contract_version = str(runtime.get("api_contract_version") or "")
        if not any(tag in contract_version for tag in SUPPORTED_API_CONTRACT_TAGS):
            expected = ", ".join(SUPPORTED_API_CONTRACT_TAGS)
            raise NutriPointsContractError(
                "Nutri Points API contract is incompatible. "
                f"Expected one of [{expected}] in api_contract_version, got '{contract_version}'."
            )
        return runtime

    async def async_get_today_status(self) -> dict[str, Any]:
        url = f"{self._base_url}{TODAY_ENDPOINT}"
        try:
            async with self._session.request(
                "GET",
                url,
                headers=self._headers(with_idempotency=False),
                ssl=self._verify_ssl,
            ) as response:
                if response.status == 401:
                    raise NutriPointsAuthError("Authentication failed with the provided API key.")
                payload = await response.json() if response.content_type == "application/json" else {}
                if response.status == 409 and isinstance(payload, dict):
                    detail_value = payload.get("detail")
                    detail: dict[str, Any] = detail_value if isinstance(detail_value, dict) else {}
                    if detail.get("error_code") == "budget_not_ready":
                        return {
                            "status": "setup_blocked",
                            "date": None,
                            "timezone": None,
                            "detail_message": detail.get("message"),
                            "detail_error_code": detail.get("error_code"),
                            "detail_retryable": detail.get("retryable"),
                        }
                if response.status >= 400:
                    await self._handle_error_response(response)
                return _normalize_today_status_payload(payload if isinstance(payload, dict) else {})
        except NutriPointsAuthError:
            raise
        except (ClientConnectorCertificateError, ClientSSLError) as exc:
            raise NutriPointsTlsError(
                "TLS verification failed while connecting to Nutri Points. Check the server certificate "
                "or disable TLS verification if appropriate."
            ) from exc
        except ClientConnectorError as exc:
            raise NutriPointsApiError(f"Unable to reach Nutri Points API: {exc}") from exc
        except ClientError as exc:
            raise NutriPointsApiError(f"Unable to reach Nutri Points API: {exc}") from exc

    async def async_get_weight_overview(self, *, range: str = "all") -> dict[str, Any]:
        return await self._request(method="GET", path=f"{WEIGHT_OVERVIEW_ENDPOINT}?range={range}")

    async def async_get_today_readiness(self) -> dict[str, Any]:
        return await self._request(method="GET", path=READINESS_ENDPOINT)

    async def async_stream_home_assistant_events(
        self,
        *,
        on_connect: Callable[[], Awaitable[None]] | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        url = f"{self._base_url}{HA_EVENTS_ENDPOINT}"
        try:
            async with self._session.request(
                "GET",
                url,
                headers=self._headers(with_idempotency=False),
                ssl=self._verify_ssl,
                timeout=None,
            ) as response:
                if response.status == 401:
                    raise NutriPointsAuthError("Authentication failed with the provided API key.")
                response.raise_for_status()
                if on_connect is not None:
                    await on_connect()

                event_name: str | None = None
                event_payload: dict[str, Any] = {}
                async for raw_chunk in response.content:
                    line = raw_chunk.decode("utf-8").strip()
                    if not line:
                        if event_name is not None:
                            yield event_name, event_payload
                        event_name = None
                        event_payload = {}
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("event:"):
                        event_name = line.partition(":")[2].strip()
                        continue
                    if line.startswith("data:"):
                        raw_payload = line.partition(":")[2].strip()
                        if not raw_payload:
                            event_payload = {}
                            continue
                        try:
                            parsed = json.loads(raw_payload)
                        except json.JSONDecodeError:
                            parsed = {}
                        event_payload = parsed if isinstance(parsed, dict) else {}
        except NutriPointsAuthError:
            raise
        except (ClientConnectorCertificateError, ClientSSLError) as exc:
            raise NutriPointsTlsError(
                "TLS verification failed while connecting to Nutri Points. Check the server certificate "
                "or disable TLS verification if appropriate."
            ) from exc
        except ClientResponseError as exc:
            raise NutriPointsApiError(f"Nutri Points API request failed: {exc.status} {exc.message}") from exc
        except ClientConnectorError as exc:
            raise NutriPointsApiError(f"Unable to reach Nutri Points API: {exc}") from exc
        except ClientError as exc:
            raise NutriPointsApiError(f"Unable to reach Nutri Points API: {exc}") from exc

    async def async_log_food(
        self,
        *,
        name: str,
        nutrition_entry_mode: str | None = None,
        protein_g: float | None = None,
        carbs_g: float | None = None,
        fat_g: float | None = None,
        fiber_g: float | None = None,
        calories_kcal: float | None = None,
        points: int | None = None,
        meal_type: str | None = None,
        applies_to_date: str | None = None,
        logged_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name}
        if nutrition_entry_mode is not None:
            payload["nutrition_entry_mode"] = nutrition_entry_mode
        if nutrition_entry_mode == "calories":
            payload["calories_kcal"] = calories_kcal
        elif nutrition_entry_mode == "points":
            payload["points"] = points
        else:
            payload["protein_g"] = protein_g
            payload["carbs_g"] = carbs_g
            payload["fat_g"] = fat_g
            payload["fiber_g"] = fiber_g
        if meal_type is not None:
            payload["meal_type"] = meal_type
        if applies_to_date is not None:
            payload["applies_to_date"] = applies_to_date
        if logged_at is not None:
            payload["logged_at"] = logged_at.isoformat() if isinstance(logged_at, datetime) else logged_at
        return await self._request(method="POST", path=FOOD_LOG_ENDPOINT, payload=payload, with_idempotency=True)

    async def async_log_activity(
        self,
        *,
        kcal: float,
        applies_to_date: str | None = None,
        logged_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"kcal": kcal}
        if applies_to_date is not None:
            payload["applies_to_date"] = applies_to_date
        if logged_at is not None:
            payload["logged_at"] = logged_at.isoformat() if isinstance(logged_at, datetime) else logged_at
        return await self._request(method="POST", path=ACTIVITY_LOG_ENDPOINT, payload=payload, with_idempotency=True)

    async def async_get_drink_settings(self) -> dict[str, Any]:
        return await self._request(method="GET", path=DRINK_SETTINGS_ENDPOINT)

    async def async_log_drink(
        self,
        *,
        drink_type_id: int,
        volume_ml: int,
        preset_id: int | None = None,
        applies_to_date: str | None = None,
        logged_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "drink_type_id": drink_type_id,
            "volume_ml": volume_ml,
        }
        if preset_id is not None:
            payload["preset_id"] = preset_id
        if applies_to_date is not None:
            payload["applies_to_date"] = applies_to_date
        if logged_at is not None:
            payload["logged_at"] = logged_at.isoformat() if isinstance(logged_at, datetime) else logged_at
        return await self._request(method="POST", path=DRINK_LOG_ENDPOINT, payload=payload, with_idempotency=True)

    async def async_log_weight(
        self,
        *,
        weight_kg: float,
        applies_to_date: str | None = None,
        logged_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"weight_kg": weight_kg}
        if applies_to_date is not None:
            payload["applies_to_date"] = applies_to_date
        if logged_at is not None:
            payload["logged_at"] = logged_at.isoformat() if isinstance(logged_at, datetime) else logged_at
        return await self._request(method="POST", path=WEIGHT_LOG_ENDPOINT, payload=payload, with_idempotency=True)

    async def async_set_steps(
        self,
        *,
        steps: int,
        mode: str = "replace_total",
        applies_to_date: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"steps": steps, "mode": mode}
        if applies_to_date is not None:
            payload["applies_to_date"] = applies_to_date
        return await self._request(method="PUT", path=STEPS_LOG_ENDPOINT, payload=payload, with_idempotency=True)
