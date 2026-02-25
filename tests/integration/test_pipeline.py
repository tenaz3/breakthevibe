"""End-to-end pipeline integration test using a local sample site."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from breakthevibe.agent.orchestrator import PipelineOrchestrator, PipelineStage

SAMPLE_SITE_DIR = Path(__file__).parent.parent / "fixtures" / "sample_site"


@pytest.mark.integration
class TestEndToEndPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_with_mock_components(self) -> None:
        """Test the orchestrator coordinates stages correctly."""
        orchestrator = PipelineOrchestrator(
            crawler=AsyncMock(),
            mapper=AsyncMock(),
            generator=AsyncMock(),
            runner=AsyncMock(),
            collector=MagicMock(),
        )

        result = await orchestrator.run(
            project_id="test-proj",
            url="http://localhost:8765",
            rules_yaml="",
        )

        assert result.success is True
        assert PipelineStage.CRAWL in result.completed_stages
        assert PipelineStage.MAP in result.completed_stages
        assert PipelineStage.GENERATE in result.completed_stages
        assert PipelineStage.RUN in result.completed_stages
        assert PipelineStage.REPORT in result.completed_stages
        assert result.duration_seconds > 0

    def test_sample_site_exists(self) -> None:
        """Verify sample site files are present."""
        assert (SAMPLE_SITE_DIR / "index.html").exists()
        assert (SAMPLE_SITE_DIR / "products.html").exists()
        assert (SAMPLE_SITE_DIR / "api" / "products.json").exists()

    def test_sample_site_index_has_structure(self) -> None:
        """Verify sample site has expected structure."""
        content = (SAMPLE_SITE_DIR / "index.html").read_text()
        assert "data-testid" in content
        assert "nav-home" in content
        assert "cta-btn" in content

    def test_sample_site_products_has_structure(self) -> None:
        """Verify products page has expected structure."""
        content = (SAMPLE_SITE_DIR / "products.html").read_text()
        assert "category-filter" in content
        assert "product-grid" in content

    @pytest.mark.asyncio
    async def test_pipeline_partial_failure_reports_stage(self) -> None:
        """Test that pipeline reports which stage failed."""
        mapper_mock = AsyncMock()
        mapper_mock.build.side_effect = Exception("LLM unavailable")
        orchestrator = PipelineOrchestrator(
            crawler=AsyncMock(),
            mapper=mapper_mock,
            generator=AsyncMock(),
            runner=AsyncMock(),
            collector=MagicMock(),
        )

        result = await orchestrator.run(
            project_id="test-proj",
            url="http://localhost:8765",
            rules_yaml="",
        )

        assert result.success is False
        assert result.failed_stage == PipelineStage.MAP
        assert "LLM unavailable" in result.error_message
