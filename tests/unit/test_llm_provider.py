import pytest

from breakthevibe.llm.provider import LLMProviderBase, LLMResponse


@pytest.mark.unit
class TestLLMProvider:
    def test_llm_response_model(self) -> None:
        resp = LLMResponse(content="Hello", model="test", tokens_used=10)
        assert resp.content == "Hello"
        assert resp.tokens_used == 10

    def test_base_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            LLMProviderBase()  # type: ignore[abstract]
