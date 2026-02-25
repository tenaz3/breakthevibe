"""Enums and type aliases for BreakTheVibe."""

from enum import StrEnum


class TestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    HEALED = "healed"
    SKIPPED = "skipped"


class TestCategory(StrEnum):
    FUNCTIONAL = "functional"
    VISUAL = "visual"
    API = "api"


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class SelectorStrategy(StrEnum):
    TEST_ID = "test_id"
    ROLE = "role"
    TEXT = "text"
    SEMANTIC = "semantic"
    STRUCTURAL = "structural"
    CSS = "css"


class ExecutionMode(StrEnum):
    SMART = "smart"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class CrawlStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
