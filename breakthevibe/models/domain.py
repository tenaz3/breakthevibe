"""Inter-module data contracts (not persisted directly)."""

from typing import Any

from pydantic import BaseModel

from breakthevibe.types import SelectorStrategy, TestCategory


class ResilientSelector(BaseModel):
    strategy: SelectorStrategy
    value: str
    name: str | None = None  # for ARIA role selectors


class ComponentInfo(BaseModel):
    name: str
    element_type: str
    selectors: list[ResilientSelector] = []
    text_content: str | None = None
    aria_role: str | None = None
    test_id: str | None = None
    is_interactive: bool = True


class InteractionInfo(BaseModel):
    name: str
    action_type: str  # click, input, scroll, select, hover
    component_name: str
    selectors: list[ResilientSelector] = []


class ApiCallInfo(BaseModel):
    url: str
    method: str
    status_code: int | None = None
    request_headers: dict[str, str] = {}
    response_headers: dict[str, str] = {}
    request_body: Any | None = None
    response_body: Any | None = None
    triggered_by: str | None = None  # component/interaction that triggered it


class PageData(BaseModel):
    url: str
    path: str
    title: str | None = None
    components: list[ComponentInfo] = []
    interactions: list[InteractionInfo] = []
    api_calls: list[ApiCallInfo] = []
    screenshot_path: str | None = None
    video_path: str | None = None
    navigates_to: list[str] = []  # paths this page links to


class SiteMap(BaseModel):
    base_url: str
    pages: list[PageData] = []
    api_endpoints: list[ApiCallInfo] = []  # deduplicated across all pages


class CrawlResult(BaseModel):
    pages: list[PageData]
    total_routes: int = 0
    total_components: int = 0
    total_api_calls: int = 0


class TestStep(BaseModel):
    action: str  # navigate, click, fill, assert_url, assert_text, api_call, screenshot
    selectors: list[ResilientSelector] = []
    target_url: str | None = None  # URL for navigate/api_call
    expected: Any | None = None  # expected value for assertions
    method: str | None = None  # HTTP method for api_call
    name: str | None = None  # screenshot name
    description: str = ""


class GeneratedTestCase(BaseModel):
    name: str
    category: TestCategory
    description: str = ""
    route: str
    steps: list[TestStep]
    code: str = ""  # executable pytest code (populated by code generator)
