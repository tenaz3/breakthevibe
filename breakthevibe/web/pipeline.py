"""Pipeline factory — builds a fully-wired PipelineOrchestrator."""

from __future__ import annotations

import uuid
from pathlib import Path

import structlog

from breakthevibe.agent.orchestrator import PipelineOrchestrator
from breakthevibe.agent.planner import AgentPlanner
from breakthevibe.config.settings import get_settings
from breakthevibe.crawler.crawler import Crawler
from breakthevibe.generator.case_builder import TestCaseGenerator
from breakthevibe.generator.code_builder import CodeBuilder
from breakthevibe.generator.rules.engine import RulesEngine
from breakthevibe.llm.factory import create_llm_provider
from breakthevibe.mapper.builder import MindMapBuilder
from breakthevibe.mapper.classifier import ComponentClassifier
from breakthevibe.reporter.collector import ResultCollector
from breakthevibe.runner.executor import TestExecutor
from breakthevibe.runner.parallel import ParallelScheduler
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
    artifacts = ArtifactStore(base_dir=Path(settings.artifacts_dir).expanduser())

    # Rules engine (always available, uses defaults if no YAML)
    rules = RulesEngine.from_yaml(rules_yaml)

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
    elif settings.ollama_base_url:
        llm = create_llm_provider("ollama", base_url=settings.ollama_base_url)

    # Components
    run_dir = artifacts.get_run_dir(project_id, run_id)
    crawler = Crawler(
        artifacts=artifacts,
        project_id=project_id,
        run_id=run_id,
        rules=rules,
    )

    mapper = MindMapBuilder(classifier=classifier)
    code_builder = CodeBuilder()
    generator = TestCaseGenerator(llm=llm, rules=rules) if llm else None

    # Runner — test output dir under the run's artifact directory
    test_output_dir = run_dir / "tests"
    test_output_dir.mkdir(parents=True, exist_ok=True)
    runner = TestExecutor(output_dir=test_output_dir)

    scheduler = ParallelScheduler(rules=rules)
    collector = ResultCollector()

    orchestrator = PipelineOrchestrator(
        crawler=crawler,
        mapper=mapper,
        generator=generator,
        runner=runner,
        collector=collector,
        planner=planner,
        code_builder=code_builder,
        scheduler=scheduler,
        max_retries=rules.get_max_retries(),
    )

    logger.info("pipeline_built", project_id=project_id, has_llm=llm is not None)
    return orchestrator
