"""Rules engine providing query methods over parsed config."""

from __future__ import annotations

import fnmatch
from typing import Any

import structlog

from breakthevibe.generator.rules.schema import RulesConfig

logger = structlog.get_logger(__name__)


class RulesEngine:
    """Query interface over a RulesConfig."""

    def __init__(self, config: RulesConfig) -> None:
        self._config = config

    @classmethod
    def from_yaml(cls, yaml_str: str) -> RulesEngine:
        """Create a RulesEngine from a YAML string."""
        config = RulesConfig.from_yaml(yaml_str)
        return cls(config)

    @property
    def config(self) -> RulesConfig:
        return self._config

    def should_skip_url(self, url: str) -> bool:
        """Check if URL matches any skip pattern (supports glob)."""
        return any(fnmatch.fnmatch(url, p) for p in self._config.crawl.skip_urls)

    def get_input_value(self, field_name: str) -> str | None:
        """Get a predefined input value for a field name."""
        return self._config.inputs.values.get(field_name)

    def get_all_inputs(self) -> dict[str, str]:
        """Get all predefined input values."""
        return dict(self._config.inputs.values)

    def should_skip_visual(self, route: str) -> bool:
        """Check if visual regression should be skipped for a route."""
        return route in self._config.tests.skip_visual

    def should_ignore_endpoint(self, endpoint: str) -> bool:
        """Check if an API endpoint should be ignored (supports glob)."""
        return any(fnmatch.fnmatch(endpoint, p) for p in self._config.api.ignore_endpoints)

    def get_expected_override(
        self, method: str, path: str
    ) -> dict[str, Any] | None:
        """Get expected response override for a specific endpoint."""
        key = f"{method} {path}"
        return self._config.api.expected_overrides.get(key)

    def get_execution_mode(self) -> str:
        """Get the global execution mode (smart/sequential/parallel)."""
        return self._config.execution.mode

    def get_suite_config(self, suite_name: str) -> dict[str, Any] | None:
        """Get execution config for a specific test suite."""
        return self._config.execution.suites.get(suite_name)

    def get_cookie_banner_action(self) -> str:
        """Get action for cookie banners."""
        return self._config.interactions.cookie_banner

    def get_modal_action(self) -> str:
        """Get action for modals."""
        return self._config.interactions.modals

    def get_scroll_behavior(self) -> str:
        """Get scroll behavior setting."""
        return self._config.crawl.scroll_behavior

    def get_infinite_scroll_action(self) -> str:
        """Get action for infinite scroll."""
        return self._config.interactions.infinite_scroll

    def get_viewport(self) -> dict[str, int]:
        """Get viewport configuration."""
        return self._config.crawl.viewport.model_dump()

    def get_wait_times(self) -> dict[str, int]:
        """Get wait time configuration."""
        return self._config.crawl.wait_times.model_dump()

    def get_max_depth(self) -> int:
        """Get maximum crawl depth."""
        return self._config.crawl.max_depth

    def to_yaml(self) -> str:
        """Serialize rules back to YAML."""
        return self._config.to_yaml()
