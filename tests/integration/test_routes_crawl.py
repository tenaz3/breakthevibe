import pytest
from httpx import ASGITransport, AsyncClient

from breakthevibe.web.app import create_app


@pytest.mark.integration
class TestCrawlRoutes:
    @pytest.fixture()
    def app(self):
        return create_app()

    @pytest.fixture()
    async def project_id(self, app) -> str:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/projects",
                json={"name": "Test", "url": "https://example.com"},
            )
            return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_trigger_crawl(self, app, project_id: str) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/projects/{project_id}/crawl")
            assert resp.status_code in (200, 202)
            data = resp.json()
            assert "status" in data

    @pytest.mark.asyncio
    async def test_crawl_nonexistent_project(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/projects/bad-id/crawl")
            assert resp.status_code == 404


@pytest.mark.integration
class TestTestRoutes:
    @pytest.fixture()
    def app(self):
        return create_app()

    @pytest.fixture()
    async def project_id(self, app) -> str:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/projects",
                json={"name": "Test", "url": "https://example.com"},
            )
            return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_trigger_generate(self, app, project_id: str) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/projects/{project_id}/generate")
            assert resp.status_code in (200, 202)

    @pytest.mark.asyncio
    async def test_trigger_run(self, app, project_id: str) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/projects/{project_id}/run")
            assert resp.status_code in (200, 202)


@pytest.mark.integration
class TestResultRoutes:
    @pytest.fixture()
    def app(self):
        return create_app()

    @pytest.mark.asyncio
    async def test_get_run_results(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/runs/test-run-id/results")
            assert resp.status_code in (200, 404)
