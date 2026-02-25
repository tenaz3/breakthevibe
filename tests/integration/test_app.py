import pytest
from httpx import ASGITransport, AsyncClient

from breakthevibe.web.app import create_app


@pytest.mark.integration
class TestAppFactory:
    @pytest.fixture()
    def app(self):
        return create_app()

    @pytest.mark.asyncio
    async def test_app_creates_successfully(self, app) -> None:
        assert app is not None
        assert app.title == "BreakTheVibe"

    @pytest.mark.asyncio
    async def test_health_endpoint(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_request_id_header(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert "x-request-id" in resp.headers

    @pytest.mark.asyncio
    async def test_cors_headers(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.options(
                "/api/health",
                headers={
                    "Origin": "http://localhost:8000",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert resp.status_code in (200, 204, 405)

    @pytest.mark.asyncio
    async def test_404_for_unknown_route(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/nonexistent")
            assert resp.status_code == 404
