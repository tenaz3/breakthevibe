import pytest

from breakthevibe.constants import DEFAULT_MAX_DEPTH, DEFAULT_VIEWPORT_WIDTH
from breakthevibe.exceptions import (
    BreakTheVibeError,
    CrawlerError,
    GeneratorError,
    LLMProviderError,
    MapperError,
    RunnerError,
    StorageError,
)
from breakthevibe.types import (
    CrawlStatus,
    ExecutionMode,
    LLMProvider,
    SelectorStrategy,
    TestCategory,
    TestStatus,
)


@pytest.mark.unit
class TestEnums:
    def test_test_status_values(self) -> None:
        assert TestStatus.PENDING.value == "pending"
        assert TestStatus.RUNNING.value == "running"
        assert TestStatus.PASSED.value == "passed"
        assert TestStatus.FAILED.value == "failed"
        assert TestStatus.HEALED.value == "healed"
        assert TestStatus.SKIPPED.value == "skipped"

    def test_test_category_values(self) -> None:
        assert TestCategory.FUNCTIONAL.value == "functional"
        assert TestCategory.VISUAL.value == "visual"
        assert TestCategory.API.value == "api"

    def test_llm_provider_values(self) -> None:
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.OLLAMA.value == "ollama"

    def test_selector_strategy_order(self) -> None:
        strategies = list(SelectorStrategy)
        assert strategies[0] == SelectorStrategy.TEST_ID
        assert strategies[-1] == SelectorStrategy.CSS

    def test_execution_mode_values(self) -> None:
        assert ExecutionMode.SMART.value == "smart"
        assert ExecutionMode.SEQUENTIAL.value == "sequential"
        assert ExecutionMode.PARALLEL.value == "parallel"

    def test_crawl_status_values(self) -> None:
        assert CrawlStatus.PENDING.value == "pending"
        assert CrawlStatus.COMPLETED.value == "completed"


@pytest.mark.unit
class TestExceptions:
    def test_base_exception_hierarchy(self) -> None:
        assert issubclass(CrawlerError, BreakTheVibeError)
        assert issubclass(MapperError, BreakTheVibeError)
        assert issubclass(LLMProviderError, BreakTheVibeError)
        assert issubclass(GeneratorError, BreakTheVibeError)
        assert issubclass(RunnerError, BreakTheVibeError)
        assert issubclass(StorageError, BreakTheVibeError)

    def test_exception_message(self) -> None:
        err = CrawlerError("page not found")
        assert str(err) == "page not found"

    def test_exceptions_catchable_as_base(self) -> None:
        with pytest.raises(BreakTheVibeError):
            raise RunnerError("test failed")


@pytest.mark.unit
class TestConstants:
    def test_defaults_exist(self) -> None:
        assert DEFAULT_VIEWPORT_WIDTH == 1280
        assert DEFAULT_MAX_DEPTH == 5
