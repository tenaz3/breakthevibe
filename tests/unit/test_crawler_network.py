from unittest.mock import AsyncMock, MagicMock

import pytest

from breakthevibe.crawler.network import NetworkInterceptor


@pytest.mark.unit
class TestNetworkInterceptor:
    def test_initial_state(self) -> None:
        interceptor = NetworkInterceptor()
        assert interceptor.get_captured_calls() == []

    def test_captures_xhr_request(self) -> None:
        interceptor = NetworkInterceptor()
        mock_request = MagicMock()
        mock_request.resource_type = "xhr"
        mock_request.url = "https://example.com/api/data"
        mock_request.method = "GET"
        mock_request.headers = {"content-type": "application/json"}
        mock_request.post_data = None

        interceptor.on_request(mock_request)
        calls = interceptor.get_captured_calls()
        assert len(calls) == 1
        assert calls[0]["url"] == "https://example.com/api/data"
        assert calls[0]["method"] == "GET"

    def test_ignores_non_api_resources(self) -> None:
        interceptor = NetworkInterceptor()
        mock_request = MagicMock()
        mock_request.resource_type = "image"
        mock_request.url = "https://example.com/logo.png"

        interceptor.on_request(mock_request)
        assert interceptor.get_captured_calls() == []

    @pytest.mark.asyncio
    async def test_on_response_captures_status(self) -> None:
        interceptor = NetworkInterceptor()

        mock_request = MagicMock()
        mock_request.resource_type = "fetch"
        mock_request.url = "https://example.com/api/users"
        mock_request.method = "POST"
        mock_request.headers = {}
        mock_request.post_data = '{"name": "test"}'
        interceptor.on_request(mock_request)

        mock_response = MagicMock()
        mock_response.url = "https://example.com/api/users"
        mock_response.status = 201
        mock_response.headers = {"content-type": "application/json"}
        mock_response.body = AsyncMock(return_value=b'{"id": 1}')

        await interceptor.on_response(mock_response)
        calls = interceptor.get_captured_calls()
        assert calls[0]["status_code"] == 201

    def test_clear_resets(self) -> None:
        interceptor = NetworkInterceptor()
        mock_request = MagicMock()
        mock_request.resource_type = "xhr"
        mock_request.url = "https://example.com/api"
        mock_request.method = "GET"
        mock_request.headers = {}
        mock_request.post_data = None
        interceptor.on_request(mock_request)

        interceptor.clear()
        assert interceptor.get_captured_calls() == []
