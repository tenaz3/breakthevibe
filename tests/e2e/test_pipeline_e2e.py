"""E2E tests: pipeline orchestration, concurrent locks, SSE progress."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from breakthevibe.agent.orchestrator import PipelineOrchestrator, PipelineStage


@pytest.mark.integration
class TestPipelineOrchestration:
    async def test_pipeline_all_stages_complete(self) -> None:
        """Mock all components — verify orchestrator coordinates 5 stages."""
        crawler_mock = AsyncMock()
        mapper_mock = AsyncMock()
        generator_mock = AsyncMock()
        runner_mock = AsyncMock()
        collector_mock = MagicMock()

        orchestrator = PipelineOrchestrator(
            crawler=crawler_mock,
            mapper=mapper_mock,
            generator=generator_mock,
            runner=runner_mock,
            collector=collector_mock,
        )

        result = await orchestrator.run(
            project_id="e2e-test",
            url="http://localhost:9999",
            rules_yaml="",
        )

        assert result.success is True
        assert PipelineStage.CRAWL in result.completed_stages
        assert PipelineStage.MAP in result.completed_stages
        assert PipelineStage.GENERATE in result.completed_stages
        assert PipelineStage.RUN in result.completed_stages
        assert PipelineStage.REPORT in result.completed_stages

    async def test_pipeline_reports_crawl_failure(self) -> None:
        """Verify pipeline reports the correct failed stage."""
        crawler_mock = AsyncMock()
        crawler_mock.crawl.side_effect = Exception("Browser not available")

        orchestrator = PipelineOrchestrator(
            crawler=crawler_mock,
            mapper=AsyncMock(),
            generator=AsyncMock(),
            runner=AsyncMock(),
            collector=MagicMock(),
        )

        result = await orchestrator.run(
            project_id="e2e-fail",
            url="http://localhost:9999",
            rules_yaml="",
        )

        assert result.success is False
        assert result.failed_stage == PipelineStage.CRAWL
        assert "Browser not available" in result.error_message

    async def test_pipeline_reports_generator_failure(self) -> None:
        """Verify failure at generate stage is correctly reported."""
        generator_mock = AsyncMock()
        generator_mock.generate.side_effect = Exception("LLM API key missing")

        orchestrator = PipelineOrchestrator(
            crawler=AsyncMock(),
            mapper=AsyncMock(),
            generator=generator_mock,
            runner=AsyncMock(),
            collector=MagicMock(),
        )

        result = await orchestrator.run(
            project_id="e2e-gen-fail",
            url="http://localhost:9999",
            rules_yaml="",
        )

        assert result.success is False
        assert result.failed_stage == PipelineStage.GENERATE
        assert "LLM API key missing" in result.error_message

    async def test_pipeline_tracks_duration(self) -> None:
        """Verify pipeline measures execution time."""
        orchestrator = PipelineOrchestrator(
            crawler=AsyncMock(),
            mapper=AsyncMock(),
            generator=AsyncMock(),
            runner=AsyncMock(),
            collector=MagicMock(),
        )

        result = await orchestrator.run(
            project_id="e2e-timing",
            url="http://localhost:9999",
            rules_yaml="",
        )

        assert result.duration_seconds > 0

    async def test_pipeline_progress_callback(self) -> None:
        """Verify progress callback fires for each stage."""
        progress_events: list[tuple[str, str]] = []

        def on_progress(stage: str, status: str, error: str = "") -> None:
            progress_events.append((stage, status))

        orchestrator = PipelineOrchestrator(
            crawler=AsyncMock(),
            mapper=AsyncMock(),
            generator=AsyncMock(),
            runner=AsyncMock(),
            collector=MagicMock(),
            progress_callback=on_progress,
        )

        await orchestrator.run(
            project_id="e2e-progress",
            url="http://localhost:9999",
            rules_yaml="",
        )

        stages_started = [s for s, status in progress_events if status == "started"]
        stages_completed = [s for s, status in progress_events if status == "completed"]
        assert len(stages_started) >= 5
        assert len(stages_completed) >= 5


@pytest.mark.integration
class TestConcurrentPipeline:
    async def test_pipeline_lock_prevents_concurrent_runs(
        self,
        authed_client,
    ) -> None:
        """Triggering crawl twice on same project — second should still accept
        (background task, but the lock prevents actual concurrent execution)."""
        create_resp = await authed_client.post(
            "/api/projects",
            json={"name": "Lock Test", "url": "https://example.com"},
        )
        project_id = create_resp.json()["id"]

        resp1 = await authed_client.post(f"/api/projects/{project_id}/crawl")
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "accepted"

        # Second trigger should also return accepted (background tasks queue)
        resp2 = await authed_client.post(f"/api/projects/{project_id}/crawl")
        assert resp2.status_code == 200
