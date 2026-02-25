"""Network traffic interceptor for capturing API calls during crawling."""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

API_RESOURCE_TYPES = {"xhr", "fetch"}


class NetworkInterceptor:
    def __init__(self) -> None:
        self._calls: list[dict[str, Any]] = []
        self._pending: dict[int, dict[str, Any]] = {}  # keyed by request id
        self._current_action: str | None = None
        self._request_counter: int = 0

    def set_current_action(self, action: str | None) -> None:
        """Set the current UI action label for attribution."""
        self._current_action = action

    def on_request(self, request: Any) -> None:
        """Handle intercepted request."""
        if request.resource_type not in API_RESOURCE_TYPES:
            return

        self._request_counter += 1
        req_id = self._request_counter

        call_data: dict[str, Any] = {
            "_req_id": req_id,
            "url": request.url,
            "method": request.method,
            "request_headers": dict(request.headers),
            "request_body": request.post_data,
            "status_code": None,
            "response_headers": {},
            "response_body": None,
            "triggered_by": self._current_action,
        }
        self._pending[req_id] = call_data
        self._calls.append(call_data)

    async def on_response(self, response: Any) -> None:
        """Handle intercepted response."""
        # Find the pending request matching this response URL (FIFO for same URL)
        matched_id: int | None = None
        for req_id, call_data in self._pending.items():
            if call_data["url"] == response.url:
                matched_id = req_id
                break
        if matched_id is not None:
            call_data = self._pending.pop(matched_id)
            call_data["status_code"] = response.status
            call_data["response_headers"] = dict(response.headers)
            try:
                body = await response.body()
                call_data["response_body"] = body.decode("utf-8", errors="replace")
            except Exception:
                call_data["response_body"] = None

    def get_captured_calls(self) -> list[dict[str, Any]]:
        """Return all captured API calls."""
        return list(self._calls)

    def clear(self) -> None:
        """Clear all captured data."""
        self._calls.clear()
        self._pending.clear()
        self._request_counter = 0
