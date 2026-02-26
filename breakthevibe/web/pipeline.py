"""Pipeline factory — builds a fully-wired PipelineOrchestrator."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

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


async def build_pipeline(
    project_id: str,
    url: str,
    rules_yaml: str = "",
    progress_callback: Callable[[str, str, str], None] | None = None,
) -> PipelineOrchestrator:
    """Build a fully-wired pipeline orchestrator with real components."""
    settings = get_settings()
    run_id = str(uuid.uuid4())

    # Artifact storage
    artifacts = ArtifactStore(base_dir=Path(settings.artifacts_dir).expanduser())

    # Rules engine (always available, uses defaults if no YAML)
    rules = RulesEngine.from_yaml(rules_yaml)

    # LLM provider — check per-module settings from DB first, fall back to env vars
    from breakthevibe.web.dependencies import llm_settings_repo

    llm_settings: dict[str, Any] = {}
    try:
        llm_settings = await llm_settings_repo.get_all()
    except (OSError, ValueError, KeyError):
        logger.warning("llm_settings_load_failed")

    def _resolve_llm(module_name: str | None = None) -> Any:
        """Resolve LLM provider for a module, checking DB settings then env."""
        modules = llm_settings.get("modules", {})
        mod_cfg = modules.get(module_name, {}) if module_name else {}
        provider = mod_cfg.get("provider") or llm_settings.get("default_provider")
        model = mod_cfg.get("model") or llm_settings.get("default_model")

        # Try provider from settings, then fall back to env
        api_key = llm_settings.get("anthropic_api_key") or settings.anthropic_api_key
        openai_key = llm_settings.get("openai_api_key") or settings.openai_api_key
        ollama_url = llm_settings.get("ollama_base_url") or settings.ollama_base_url

        if provider == "openai" and openai_key:
            return create_llm_provider("openai", api_key=openai_key, model=model)
        if provider == "ollama" and ollama_url:
            return create_llm_provider("ollama", base_url=ollama_url, model=model)
        if api_key:
            return create_llm_provider("anthropic", api_key=api_key, model=model)
        if openai_key:
            return create_llm_provider("openai", api_key=openai_key, model=model)
        if ollama_url:
            return create_llm_provider("ollama", base_url=ollama_url, model=model)
        return None

    # Create per-module LLM instances (with fallback to a shared default)
    llm = _resolve_llm("generator")
    mapper_llm = _resolve_llm("mapper") or llm
    agent_llm = _resolve_llm("agent") or llm

    planner = AgentPlanner(llm=agent_llm) if agent_llm else None
    classifier = ComponentClassifier(llm=mapper_llm) if mapper_llm else None

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
    runner = TestExecutor(
        output_dir=test_output_dir,
        max_reruns=rules.get_max_retries(),
    )

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
        progress_callback=progress_callback,
    )

    logger.info("pipeline_built", project_id=project_id, has_llm=llm is not None)
    return orchestrator
