import pytest


@pytest.mark.integration
class TestProjectRoutes:
    @pytest.mark.asyncio
    async def test_create_project(self, authed_client) -> None:
        resp = await authed_client.post(
            "/api/projects",
            json={"name": "Test Site", "url": "https://example.com"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Site"
        assert data["url"] == "https://example.com/"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_projects(self, authed_client) -> None:
        await authed_client.post(
            "/api/projects",
            json={"name": "Site A", "url": "https://a.com"},
        )
        resp = await authed_client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_project(self, authed_client) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Site B", "url": "https://b.com"},
        )
        project_id = create_resp.json()["id"]
        resp = await authed_client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Site B"

    @pytest.mark.asyncio
    async def test_get_nonexistent_project(self, authed_client) -> None:
        resp = await authed_client.get("/api/projects/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project(self, authed_client) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "To Delete", "url": "https://delete.com"},
        )
        project_id = create_resp.json()["id"]
        del_resp = await authed_client.delete(f"/api/projects/{project_id}")
        assert del_resp.status_code == 204
        get_resp = await authed_client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_project_validation(self, authed_client) -> None:
        resp = await authed_client.post(
            "/api/projects",
            json={"name": "", "url": "not-a-url"},
        )
        assert resp.status_code == 422
