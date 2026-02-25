"""Network traffic interceptor for capturing API calls during crawling."""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

API_RESOURCE_TYPES = {"xhr", "fetch"}


class NetworkInterceptor:
    def __init__(self) -> None:
        self._calls: list[dict[str, Any]] = []
        self._pending: dict[str, dict[str, Any]] = {}
        self._current_action: str | None = None

    def set_current_action(self, action: str | None) -> None:
        """Set the current UI action label for attribution."""
        self._current_action = action

    def on_request(self, request: Any) -> None:
        """Handle intercepted request."""
        if request.resource_type not in API_RESOURCE_TYPES:
            return

        call_data: dict[str, Any] = {
            "url": request.url,
            "method": request.method,
            "request_headers": dict(request.headers),
            "request_body": request.post_data,
            "status_code": None,
            "response_headers": {},
            "response_body": None,
            "triggered_by": self._current_action,
        }
        self._pending[request.url] = call_data
        self._calls.append(call_data)

    async def on_response(self, response: Any) -> None:
        """Handle intercepted response."""
        url = response.url
        if url in self._pending:
            call_data = self._pending[url]
            call_data["status_code"] = response.status
            call_data["response_headers"] = dict(response.headers)
            try:
                body = await response.body()
                call_data["response_body"] = body.decode("utf-8", errors="replace")
            except Exception:
                call_data["response_body"] = None
            del self._pending[url]

    def get_captured_calls(self) -> list[dict[str, Any]]:
        """Return all captured API calls."""
        return list(self._calls)

    def clear(self) -> None:
        """Clear all captured data."""
        self._calls.clear()
        self._pending.clear()
