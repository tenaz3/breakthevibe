"""Pipeline factory — builds a fully-wired PipelineOrchestrator."""

from __future__ import annotations

import uuid

import structlog

from breakthevibe.agent.orchestrator import PipelineOrchestrator
from breakthevibe.agent.planner import AgentPlanner
from breakthevibe.config.settings import get_settings
from breakthevibe.crawler.crawler import Crawler
from breakthevibe.generator.case_builder import TestCaseGenerator
from breakthevibe.llm.factory import create_llm_provider
from breakthevibe.mapper.builder import MindMapBuilder
from breakthevibe.mapper.classifier import ComponentClassifier
from breakthevibe.reporter.collector import ResultCollector
from breakthevibe.storage.artifacts import ArtifactStore

logger = structlog.get_logger(__name__)


def build_pipeline(
    project_id: str,
    url: str,
    rules_yaml: str = "",
) -> PipelineOrchestrator:
    """Build a fully-wired pipeline orchestrator with real components."""
    settings = get_settings()
    run_id = str(uuid.uuid4())

    # Artifact storage
    from pathlib import Path

    artifacts = ArtifactStore(base_dir=Path(settings.artifacts_dir).expanduser())

    # LLM provider (if API key available)
    llm = None
    planner = None
    classifier = None
    if settings.anthropic_api_key:
        llm = create_llm_provider("anthropic", api_key=settings.anthropic_api_key)
        planner = AgentPlanner(llm=llm)
        classifier = ComponentClassifier(llm=llm)
    elif settings.openai_api_key:
        llm = create_llm_provider("openai", api_key=settings.openai_api_key)
        planner = AgentPlanner(llm=llm)
        classifier = ComponentClassifier(llm=llm)

    # Components
    crawler = Crawler(
        artifacts=artifacts,
        project_id=project_id,
        run_id=run_id,
    )

    mapper = MindMapBuilder(classifier=classifier)

    generator = TestCaseGenerator(llm=llm) if llm else None
    collector = ResultCollector()

    orchestrator = PipelineOrchestrator(
        crawler=crawler,
        mapper=mapper,
        generator=generator,
        runner=None,  # Runner is created per test suite
        collector=collector,
        planner=planner,
    )

    logger.info("pipeline_built", project_id=project_id, has_llm=llm is not None)
    return orchestrator
