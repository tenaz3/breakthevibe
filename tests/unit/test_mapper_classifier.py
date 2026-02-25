import json
from unittest.mock import AsyncMock

import pytest

from breakthevibe.llm.provider import LLMResponse
from breakthevibe.mapper.classifier import ComponentClassifier
from breakthevibe.models.domain import ComponentInfo, ResilientSelector
from breakthevibe.types import SelectorStrategy

SAMPLE_COMPONENTS = [
    ComponentInfo(
        name="Home",
        element_type="a",
        selectors=[ResilientSelector(strategy=SelectorStrategy.TEXT, value="Home")],
        aria_role="link",
    ),
    ComponentInfo(
        name="About",
        element_type="a",
        selectors=[ResilientSelector(strategy=SelectorStrategy.TEXT, value="About")],
        aria_role="link",
    ),
    ComponentInfo(
        name="Submit",
        element_type="button",
        selectors=[ResilientSelector(strategy=SelectorStrategy.TEXT, value="Submit")],
        aria_role="button",
    ),
]

MOCK_LLM_RESPONSE = json.dumps(
    {
        "groups": [
            {
                "group_name": "Navigation Bar",
                "group_type": "navigation",
                "components": ["Home", "About"],
            },
            {
                "group_name": "Form Actions",
                "group_type": "form",
                "components": ["Submit"],
            },
        ]
    }
)


@pytest.mark.unit
class TestComponentClassifier:
    @pytest.mark.asyncio
    async def test_classify_groups_components(self) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate_structured = AsyncMock(
            return_value=LLMResponse(content=MOCK_LLM_RESPONSE, model="test", tokens_used=100)
        )

        classifier = ComponentClassifier(llm=mock_llm)
        groups = await classifier.classify(SAMPLE_COMPONENTS, page_url="https://example.com/")

        assert len(groups) == 2
        assert groups[0]["group_name"] == "Navigation Bar"
        assert "Home" in groups[0]["components"]
        assert "About" in groups[0]["components"]
        assert groups[1]["group_name"] == "Form Actions"

    @pytest.mark.asyncio
    async def test_classify_sends_component_summary(self) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate_structured = AsyncMock(
            return_value=LLMResponse(content='{"groups": []}', model="test", tokens_used=50)
        )

        classifier = ComponentClassifier(llm=mock_llm)
        await classifier.classify(SAMPLE_COMPONENTS, page_url="https://example.com/")

        call_args = mock_llm.generate_structured.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "Home" in prompt
        assert "Submit" in prompt

    @pytest.mark.asyncio
    async def test_classify_empty_components(self) -> None:
        mock_llm = AsyncMock()
        classifier = ComponentClassifier(llm=mock_llm)
        groups = await classifier.classify([], page_url="https://example.com/")
        assert groups == []
        mock_llm.generate_structured.assert_not_called()
