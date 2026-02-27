"""E2E tests: auth flows, project CRUD, settings, rules, static assets."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.integration
class TestAuthFlow:
    async def test_unauthenticated_api_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/projects")
        assert resp.status_code == 401

    async def test_unauthenticated_page_redirects_to_login(self, client: AsyncClient) -> None:
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/login" in resp.headers["location"]

    async def test_login_page_accessible_without_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/login")
        assert resp.status_code == 200
        assert "Sign in" in resp.text

    async def test_login_sets_session_cookie(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["username"] == "admin"
        assert "session" in resp.cookies

    async def test_login_rejects_empty_credentials(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/auth/login",
            json={"username": "", "password": ""},
        )
        assert resp.status_code == 400

    async def test_logout_clears_session(self, authed_client: AsyncClient) -> None:
        # Verify authenticated first
        resp = await authed_client.get("/api/projects")
        assert resp.status_code == 200

        # Logout
        resp = await authed_client.post("/api/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["status"] == "logged_out"

    async def test_login_page_redirects_if_already_authed(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.get("/login", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"


@pytest.mark.integration
class TestProjectCRUD:
    async def test_create_project(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.post(
            "/api/projects",
            json={"name": "Test Project", "url": "https://example.com"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Project"
        assert data["url"] == "https://example.com/"
        assert data["status"] == "created"
        assert "id" in data

    async def test_list_projects(self, authed_client: AsyncClient) -> None:
        # Create a project first
        await authed_client.post(
            "/api/projects",
            json={"name": "List Test", "url": "https://example.com"},
        )
        resp = await authed_client.get("/api/projects")
        assert resp.status_code == 200
        projects = resp.json()
        assert isinstance(projects, list)
        assert len(projects) >= 1
        names = [p["name"] for p in projects]
        assert "List Test" in names

    async def test_get_project_by_id(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Get Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Test"

    async def test_get_nonexistent_project_returns_404(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.get("/api/projects/99999")
        assert resp.status_code == 404

    async def test_delete_project(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Delete Me", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.delete(f"/api/projects/{project_id}")
        assert resp.status_code == 204

        # Verify deleted
        resp = await authed_client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 404

    async def test_delete_nonexistent_project_returns_404(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.delete("/api/projects/99999")
        assert resp.status_code == 404

    async def test_create_project_with_rules(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.post(
            "/api/projects",
            json={
                "name": "Rules Project",
                "url": "https://example.com",
                "rules_yaml": "crawl:\n  max_depth: 2",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["rules_yaml"] == "crawl:\n  max_depth: 2"


@pytest.mark.integration
class TestCrawlTrigger:
    async def test_crawl_nonexistent_project_returns_404(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.post("/api/projects/99999/crawl")
        assert resp.status_code == 404

    async def test_crawl_returns_accepted(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Crawl Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.post(f"/api/projects/{project_id}/crawl")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["project_id"] == project_id

    async def test_sitemap_returns_empty_before_crawl(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Sitemap Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.get(f"/api/projects/{project_id}/sitemap")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pages"] == []
        assert data["api_endpoints"] == []


@pytest.mark.integration
class TestResults:
    async def test_project_results_no_runs(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Results Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.get(f"/api/projects/{project_id}/results")
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_runs"

    async def test_run_results_not_found(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.get("/api/runs/nonexistent-run-id/results")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_found"


@pytest.mark.integration
class TestRulesValidation:
    async def test_validate_valid_yaml(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.post(
            "/api/rules/validate",
            json={"yaml": "crawl:\n  max_depth: 3"},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    async def test_validate_invalid_yaml(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.post(
            "/api/rules/validate",
            json={"yaml": "crawl:\n  max_depth: [invalid"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "error" in data

    async def test_validate_empty_yaml(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.post(
            "/api/rules/validate",
            json={"yaml": ""},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True


@pytest.mark.integration
class TestHealthAndInfra:
    async def test_health_no_auth_required(self, client: AsyncClient) -> None:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data

    async def test_request_id_header(self, client: AsyncClient) -> None:
        resp = await client.get("/api/health")
        assert "x-request-id" in resp.headers

    async def test_404_for_unknown_api_route(self, client: AsyncClient) -> None:
        resp = await client.get("/api/nonexistent")
        assert resp.status_code == 404


@pytest.mark.integration
class TestStaticAssets:
    async def test_css_served(self, client: AsyncClient) -> None:
        resp = await client.get("/static/css/style.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers.get("content-type", "")

    async def test_js_mindmap_served(self, client: AsyncClient) -> None:
        resp = await client.get("/static/js/mindmap.js")
        assert resp.status_code == 200

    async def test_js_replay_served(self, client: AsyncClient) -> None:
        resp = await client.get("/static/js/replay.js")
        assert resp.status_code == 200

    async def test_favicon_served(self, client: AsyncClient) -> None:
        resp = await client.get("/static/favicon.svg")
        assert resp.status_code == 200
