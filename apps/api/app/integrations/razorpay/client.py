from typing import Any

import httpx

from app.integrations.razorpay.errors import (
    RazorpayAPIError,
    RazorpayAuthenticationError,
    RazorpayRateLimitError,
    RazorpayResponseValidationError,
    RazorpayServiceError,
    RazorpayTransportError,
)


class RazorpayClient:
    def __init__(
        self,
        *,
        key_id: str,
        key_secret: str,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            auth=httpx.BasicAuth(key_id, key_secret),
            base_url=base_url.rstrip("/") + "/",
            timeout=timeout_seconds,
            transport=transport,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(method, path.lstrip("/"), json=json)
        except httpx.TimeoutException as exc:
            raise RazorpayTransportError(
                "Razorpay request timed out.", retryable=True
            ) from exc
        except httpx.RequestError as exc:
            raise RazorpayTransportError(
                "Razorpay request could not be completed.", retryable=True
            ) from exc

        if response.is_error:
            raise self._normalize_api_error(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise RazorpayResponseValidationError(
                "Razorpay returned a non-JSON response."
            ) from exc
        if not isinstance(payload, dict):
            raise RazorpayResponseValidationError(
                "Razorpay returned an unexpected response shape."
            )
        return payload

    @staticmethod
    def _normalize_api_error(response: httpx.Response) -> RazorpayAPIError:
        code = None
        description = "Razorpay API request failed."
        try:
            payload = response.json()
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            if isinstance(error, dict):
                raw_code = error.get("code")
                raw_description = error.get("description")
                code = str(raw_code) if raw_code is not None else None
                if isinstance(raw_description, str) and raw_description:
                    description = raw_description
        except ValueError:
            pass

        error_type: type[RazorpayAPIError] = RazorpayAPIError
        retryable = False
        if response.status_code in (401, 403):
            error_type = RazorpayAuthenticationError
        elif response.status_code == 429:
            error_type = RazorpayRateLimitError
            retryable = True
        elif response.status_code >= 500:
            error_type = RazorpayServiceError
            retryable = True

        return error_type(
            status_code=response.status_code,
            code=code,
            description=description,
            retryable=retryable,
        )

    def close(self) -> None:
        self._client.close()
