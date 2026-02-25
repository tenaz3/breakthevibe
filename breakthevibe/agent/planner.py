"""LLM-based agent planner for retry decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from breakthevibe.agent.orchestrator import PipelineStage

logger = structlog.get_logger(__name__)


@dataclass
class RetryDecision:
    """Decision from the planner about whether to retry."""

    should_retry: bool
    reason: str = ""
    adjusted_params: dict[str, Any] = field(default_factory=dict)


class AgentPlanner:
    """Analyzes failures and decides whether/how to retry."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm
        self.max_attempts: int = 3

    async def analyze_failure(
        self,
        stage: PipelineStage,
        error: str,
        attempt: int,
    ) -> RetryDecision:
        """Ask LLM whether to retry a failed stage."""
        if attempt >= self.max_attempts:
            logger.info("max_attempts_reached", stage=stage.value, attempt=attempt)
            return RetryDecision(
                should_retry=False,
                reason=f"Maximum attempts ({self.max_attempts}) reached",
            )

        prompt = self._build_prompt(stage, error, attempt)

        try:
            response = await self._llm.generate(prompt=prompt)
            return self._parse_decision(response.content)
        except Exception as e:
            logger.error("planner_llm_error", error=str(e))
            return RetryDecision(should_retry=False, reason=f"Planner error: {e}")

    def _build_prompt(self, stage: PipelineStage, error: str, attempt: int) -> str:
        return (
            "A pipeline stage has failed. Analyze the error and decide if retrying would help.\n"
            "\n"
            f"Stage: {stage.value}\n"
            f"Error: {error}\n"
            f"Attempt: {attempt} of {self.max_attempts}\n"
            "\n"
            "Respond with JSON:\n"
            "{\n"
            '  "should_retry": true/false,\n'
            '  "reason": "explanation",\n'
            '  "adjusted_params": {}  // optional adjusted parameters for retry\n'
            "}\n"
            "\n"
            "Consider:\n"
            "- Transient errors (timeouts, rate limits) usually benefit from retry\n"
            "- Permanent errors (invalid URL, auth failure) should not be retried\n"
            "- If retrying, suggest adjusted parameters (longer timeout, different approach)"
        )

    def _parse_decision(self, content: str) -> RetryDecision:
        """Parse LLM response into a RetryDecision."""
        try:
            data = json.loads(content)
            return RetryDecision(
                should_retry=bool(data.get("should_retry", False)),
                reason=data.get("reason", ""),
                adjusted_params=data.get("adjusted_params", {}),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("planner_parse_error", error=str(e), content=content[:200])
            return RetryDecision(
                should_retry=False,
                reason=f"Failed to parse planner response: {e}",
            )
