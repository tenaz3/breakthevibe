from unittest.mock import AsyncMock, MagicMock

import pytest

from breakthevibe.agent.orchestrator import (
    PipelineOrchestrator,
    PipelineResult,
    PipelineStage,
)


@pytest.mark.unit
class TestPipelineOrchestrator:
    @pytest.fixture()
    def mock_components(self) -> dict:
        return {
            "crawler": AsyncMock(),
            "mapper": AsyncMock(),
            "generator": AsyncMock(),
            "runner": AsyncMock(),
            "collector": MagicMock(),
        }

    @pytest.fixture()
    def orchestrator(self, mock_components: dict) -> PipelineOrchestrator:
        return PipelineOrchestrator(**mock_components)

    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, orchestrator: PipelineOrchestrator) -> None:
        result = await orchestrator.run(
            project_id="proj-1",
            url="https://example.com",
            rules_yaml="",
        )
        assert isinstance(result, PipelineResult)
        assert result.success is True
        assert result.completed_stages == [
            PipelineStage.CRAWL,
            PipelineStage.MAP,
            PipelineStage.GENERATE,
            PipelineStage.RUN,
            PipelineStage.REPORT,
        ]

    @pytest.mark.asyncio
    async def test_crawl_failure_stops_pipeline(
        self,
        orchestrator: PipelineOrchestrator,
        mock_components: dict,
    ) -> None:
        mock_components["crawler"].crawl.side_effect = Exception("Connection timeout")
        result = await orchestrator.run(
            project_id="proj-1",
            url="https://example.com",
            rules_yaml="",
        )
        assert result.success is False
        assert result.failed_stage == PipelineStage.CRAWL
        assert "Connection timeout" in result.error_message

    @pytest.mark.asyncio
    async def test_generator_failure_stops_pipeline(
        self,
        orchestrator: PipelineOrchestrator,
        mock_components: dict,
    ) -> None:
        mock_components["generator"].generate.side_effect = Exception("LLM rate limit")
        result = await orchestrator.run(
            project_id="proj-1",
            url="https://example.com",
            rules_yaml="",
        )
        assert result.success is False
        assert result.failed_stage == PipelineStage.GENERATE

    @pytest.mark.asyncio
    async def test_pipeline_records_duration(self, orchestrator: PipelineOrchestrator) -> None:
        result = await orchestrator.run(
            project_id="proj-1",
            url="https://example.com",
            rules_yaml="",
        )
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_pipeline_retries_on_failure(
        self,
        orchestrator: PipelineOrchestrator,
        mock_components: dict,
    ) -> None:
        mock_components["crawler"].crawl.side_effect = [
            Exception("Transient"),
            MagicMock(),
        ]
        orchestrator.max_retries = 2
        await orchestrator.run(
            project_id="proj-1",
            url="https://example.com",
            rules_yaml="",
        )
        assert mock_components["crawler"].crawl.call_count == 2
