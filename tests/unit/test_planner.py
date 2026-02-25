import json
from unittest.mock import AsyncMock

import pytest

from breakthevibe.agent.orchestrator import PipelineStage
from breakthevibe.agent.planner import AgentPlanner, RetryDecision
from breakthevibe.llm.provider import LLMResponse


@pytest.mark.unit
class TestAgentPlanner:
    @pytest.fixture()
    def mock_llm(self) -> AsyncMock:
        llm = AsyncMock()
        llm.generate.return_value = LLMResponse(
            content=json.dumps(
                {
                    "should_retry": True,
                    "reason": "Transient network error, retrying with longer timeout",
                    "adjusted_params": {"timeout": 10000},
                }
            ),
            model="test-model",
            tokens_used=80,
        )
        return llm

    @pytest.fixture()
    def planner(self, mock_llm: AsyncMock) -> AgentPlanner:
        return AgentPlanner(llm=mock_llm)

    @pytest.mark.asyncio
    async def test_decides_retry_on_transient(self, planner: AgentPlanner) -> None:
        decision = await planner.analyze_failure(
            stage=PipelineStage.CRAWL,
            error="ConnectionError: Connection timed out",
            attempt=1,
        )
        assert isinstance(decision, RetryDecision)
        assert decision.should_retry is True
        assert decision.reason != ""

    @pytest.mark.asyncio
    async def test_decides_no_retry_on_permanent(
        self, planner: AgentPlanner, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate.return_value = LLMResponse(
            content=json.dumps(
                {
                    "should_retry": False,
                    "reason": "Invalid URL - permanent failure",
                    "adjusted_params": {},
                }
            ),
            model="test-model",
            tokens_used=80,
        )
        decision = await planner.analyze_failure(
            stage=PipelineStage.CRAWL,
            error="Invalid URL: not-a-url",
            attempt=1,
        )
        assert decision.should_retry is False

    @pytest.mark.asyncio
    async def test_includes_adjusted_params(self, planner: AgentPlanner) -> None:
        decision = await planner.analyze_failure(
            stage=PipelineStage.CRAWL,
            error="Timeout",
            attempt=1,
        )
        assert "timeout" in decision.adjusted_params

    @pytest.mark.asyncio
    async def test_prompt_includes_context(
        self, planner: AgentPlanner, mock_llm: AsyncMock
    ) -> None:
        await planner.analyze_failure(
            stage=PipelineStage.MAP,
            error="LLM rate limit exceeded",
            attempt=2,
        )
        call_args = mock_llm.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "map" in prompt.lower()
        assert "rate limit" in prompt.lower()

    @pytest.mark.asyncio
    async def test_handles_invalid_llm_response(
        self, planner: AgentPlanner, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate.return_value = LLMResponse(
            content="invalid json response",
            model="test-model",
            tokens_used=20,
        )
        decision = await planner.analyze_failure(
            stage=PipelineStage.RUN,
            error="Some error",
            attempt=1,
        )
        assert decision.should_retry is False

    @pytest.mark.asyncio
    async def test_max_attempts_forces_no_retry(self, planner: AgentPlanner) -> None:
        planner.max_attempts = 3
        decision = await planner.analyze_failure(
            stage=PipelineStage.CRAWL,
            error="Error",
            attempt=3,
        )
        assert decision.should_retry is False
