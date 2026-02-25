import pytest


@pytest.mark.integration
class TestCrawlRoutes:
    @pytest.fixture()
    async def project_id(self, authed_client) -> str:
        resp = await authed_client.post(
            "/api/projects",
            json={"name": "Test", "url": "https://example.com"},
        )
        return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_trigger_crawl(self, authed_client, project_id: str) -> None:
        resp = await authed_client.post(f"/api/projects/{project_id}/crawl")
        assert resp.status_code in (200, 202)
        data = resp.json()
        assert "status" in data

    @pytest.mark.asyncio
    async def test_crawl_nonexistent_project(self, authed_client) -> None:
        resp = await authed_client.post("/api/projects/bad-id/crawl")
        assert resp.status_code == 404


@pytest.mark.integration
class TestTestRoutes:
    @pytest.fixture()
    async def project_id(self, authed_client) -> str:
        resp = await authed_client.post(
            "/api/projects",
            json={"name": "Test", "url": "https://example.com"},
        )
        return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_trigger_generate(self, authed_client, project_id: str) -> None:
        resp = await authed_client.post(f"/api/projects/{project_id}/generate")
        assert resp.status_code in (200, 202)

    @pytest.mark.asyncio
    async def test_trigger_run(self, authed_client, project_id: str) -> None:
        resp = await authed_client.post(f"/api/projects/{project_id}/run")
        assert resp.status_code in (200, 202)


@pytest.mark.integration
class TestResultRoutes:
    @pytest.mark.asyncio
    async def test_get_run_results(self, authed_client) -> None:
        resp = await authed_client.get("/api/runs/test-run-id/results")
        assert resp.status_code in (200, 404)
