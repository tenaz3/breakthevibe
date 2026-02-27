"""E2E tests: verify template rendering and page structure."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.integration
class TestLoginPage:
    async def test_has_login_form(self, client: AsyncClient) -> None:
        resp = await client.get("/login")
        assert resp.status_code == 200
        html = resp.text
        assert "username" in html.lower()
        assert "password" in html.lower()
        assert "Sign in" in html

    async def test_has_brand(self, client: AsyncClient) -> None:
        resp = await client.get("/login")
        assert "BreakTheVibe" in resp.text


@pytest.mark.integration
class TestProjectsPage:
    async def test_projects_page_renders(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.get("/")
        assert resp.status_code == 200
        assert "Projects" in resp.text

    async def test_has_new_project_button(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.get("/")
        assert "New Project" in resp.text

    async def test_shows_created_project(self, authed_client: AsyncClient) -> None:
        await authed_client.post(
            "/api/projects",
            json={"name": "UI Visible Project", "url": "https://example.com"},
        )
        resp = await authed_client.get("/")
        assert "UI Visible Project" in resp.text


@pytest.mark.integration
class TestProjectDetailPage:
    async def test_has_pipeline_buttons(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Detail Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.get(f"/projects/{project_id}")
        assert resp.status_code == 200
        html = resp.text
        assert "Crawl" in html
        assert "Generate" in html
        assert "Run Tests" in html
        assert "Suites" in html
        assert "Mind-Map" in html
        assert "Rules" in html

    async def test_has_tabs(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Tab Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.get(f"/projects/{project_id}")
        assert "Test Runs" in resp.text
        assert "Site Map" in resp.text

    async def test_nonexistent_project_returns_404(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.get("/projects/99999")
        assert resp.status_code == 404


@pytest.mark.integration
class TestLlmSettingsPage:
    async def test_has_provider_selects(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.get("/settings/llm")
        assert resp.status_code == 200
        html = resp.text
        assert "Anthropic" in html
        assert "OpenAI" in html
        assert "Ollama" in html

    async def test_has_api_key_inputs(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.get("/settings/llm")
        html = resp.text
        assert "anthropic_api_key" in html or "Anthropic API Key" in html
        assert "openai_api_key" in html or "OpenAI API Key" in html

    async def test_has_module_overrides(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.get("/settings/llm")
        html = resp.text
        assert "Mapper" in html
        assert "Generator" in html
        assert "Agent" in html


@pytest.mark.integration
class TestRulesEditorPage:
    async def test_has_editor(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Rules Page Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.get(f"/projects/{project_id}/rules")
        assert resp.status_code == 200
        html = resp.text
        assert "Rules Editor" in html
        assert "Save Rules" in html
        assert "Validate" in html


@pytest.mark.integration
class TestSitemapPage:
    async def test_renders_empty_mindmap(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Mindmap Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.get(f"/projects/{project_id}/sitemap")
        assert resp.status_code == 200
        assert "Mind-Map" in resp.text


@pytest.mark.integration
class TestSuitesPage:
    async def test_has_category_filters(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Suites Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.get(f"/projects/{project_id}/suites")
        assert resp.status_code == 200
        html = resp.text
        assert "Functional" in html
        assert "Visual" in html
        assert "API" in html

    async def test_has_quick_rules_editor(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Quick Rules Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.get(f"/projects/{project_id}/suites")
        assert "Quick Rules Editor" in resp.text


@pytest.mark.integration
class TestTestRunsPage:
    async def test_renders_empty(self, authed_client: AsyncClient) -> None:
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Runs Page Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp = await authed_client.get(f"/projects/{project_id}/runs")
        assert resp.status_code == 200
        assert "Test Runs" in resp.text


@pytest.mark.integration
class TestNavigation:
    async def test_nav_has_projects_link(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.get("/")
        assert 'href="/"' in resp.text or "Projects" in resp.text

    async def test_nav_has_settings_link(self, authed_client: AsyncClient) -> None:
        resp = await authed_client.get("/")
        assert "/settings/llm" in resp.text
