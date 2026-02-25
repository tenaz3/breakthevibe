"""Exception hierarchy for BreakTheVibe."""


class BreakTheVibeError(Exception):
    """Base exception for all BreakTheVibe errors."""


class CrawlerError(BreakTheVibeError):
    """Raised when the crawler encounters an error."""


class MapperError(BreakTheVibeError):
    """Raised when the mapper encounters an error."""


class GeneratorError(BreakTheVibeError):
    """Raised when test generation fails."""


class LLMProviderError(BreakTheVibeError):
    """Raised when an LLM provider call fails."""


class RunnerError(BreakTheVibeError):
    """Raised when test execution fails."""


class StorageError(BreakTheVibeError):
    """Raised when storage operations fail."""


class ConfigError(BreakTheVibeError):
    """Raised when configuration is invalid."""
