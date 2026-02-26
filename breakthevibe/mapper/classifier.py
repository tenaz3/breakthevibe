"""LLM-powered component classification and grouping."""

import json
from typing import Any

import structlog

from breakthevibe.llm.provider import LLMProviderBase
from breakthevibe.models.domain import ComponentInfo

logger = structlog.get_logger(__name__)

CLASSIFIER_SYSTEM_PROMPT = """You are an expert web UI analyst. Given a list of UI components \
extracted from a web page, group them into logical sections \
(navigation, forms, content areas, etc.).

Return JSON with this structure:
{
    "groups": [
        {
            "group_name": "descriptive name",
            "group_type": "navigation|form|content|footer|header|sidebar|modal|other",
            "components": ["component name 1", "component name 2"]
        }
    ]
}

Group by visual/functional proximity. Every component must appear in exactly one group."""


class ComponentClassifier:
    """Uses LLM to classify and group page components."""

    def __init__(self, llm: LLMProviderBase):
        self._llm = llm

    async def classify(
        self, components: list[ComponentInfo], page_url: str
    ) -> list[dict[str, Any]]:
        """Classify components into logical groups using LLM."""
        if not components:
            return []

        component_summary = "\n".join(
            f"- {c.name} ({c.element_type}, role={c.aria_role}, interactive={c.is_interactive})"
            for c in components
        )
        prompt = (
            f"Page: {page_url}\n\nComponents found:\n{component_summary}\n\nGroup these components."
        )

        response = await self._llm.generate_structured(
            prompt=prompt,
            system=CLASSIFIER_SYSTEM_PROMPT,
        )

        try:
            result = json.loads(response.content)
            groups: list[dict[str, Any]] = result.get("groups", [])
            return groups
        except json.JSONDecodeError:
            logger.warning("llm_classification_parse_error", page_url=page_url)
            return []
