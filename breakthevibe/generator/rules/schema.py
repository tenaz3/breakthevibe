"""Rules configuration schema with Pydantic validation."""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, Field


class ViewportConfig(BaseModel):
    width: int = 1280
    height: int = 800


class WaitTimesConfig(BaseModel):
    page_load: int = 3000
    after_click: int = 1000


class CrawlRules(BaseModel):
    max_depth: int = 10
    skip_urls: list[str] = Field(default_factory=list)
    scroll_behavior: str = "incremental"
    wait_times: WaitTimesConfig = Field(default_factory=WaitTimesConfig)
    viewport: ViewportConfig = Field(default_factory=ViewportConfig)


class InputRules(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any] | None) -> InputRules:
        if not data:
            return cls()
        return cls(values=data)


class InteractionRules(BaseModel):
    cookie_banner: str = "dismiss"
    modals: str = "close_on_appear"
    infinite_scroll: str = "scroll_3_times"


class TestRules(BaseModel):
    skip_visual: list[str] = Field(default_factory=list)
    custom_assertions: list[str] = Field(default_factory=list)


class ApiRules(BaseModel):
    ignore_endpoints: list[str] = Field(default_factory=list)
    expected_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SuiteConfig(BaseModel):
    mode: str = "smart"
    shared_context: bool = False
    workers: int = 1


class ExecutionRules(BaseModel):
    mode: str = "smart"
    suites: dict[str, dict[str, Any]] = Field(default_factory=dict)


class RulesConfig(BaseModel):
    crawl: CrawlRules = Field(default_factory=CrawlRules)
    inputs: InputRules = Field(default_factory=InputRules)
    interactions: InteractionRules = Field(default_factory=InteractionRules)
    tests: TestRules = Field(default_factory=TestRules)
    api: ApiRules = Field(default_factory=ApiRules)
    execution: ExecutionRules = Field(default_factory=ExecutionRules)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> RulesConfig:
        """Parse a YAML string into a RulesConfig."""
        if not yaml_str or not yaml_str.strip():
            return cls()
        raw = yaml.safe_load(yaml_str)
        if not raw or not isinstance(raw, dict):
            return cls()
        # Handle inputs specially (flat dict -> InputRules)
        inputs_data = raw.pop("inputs", None)
        config = cls.model_validate(raw)
        if inputs_data:
            config.inputs = InputRules.from_raw(inputs_data)
        return config

    def to_yaml(self) -> str:
        """Serialize config back to YAML."""
        data = self.model_dump()
        # Flatten inputs back to simple dict
        data["inputs"] = data["inputs"]["values"]
        return yaml.dump(data, default_flow_style=False, sort_keys=False)
