import pytest

from breakthevibe.generator.rules.engine import RulesEngine
from breakthevibe.generator.rules.schema import RulesConfig

SAMPLE_YAML = """
crawl:
  max_depth: 5
  skip_urls:
    - "/admin/*"
    - "/api/internal/*"
  scroll_behavior: incremental
  wait_times:
    page_load: 3000
    after_click: 1000
  viewport:
    width: 1280
    height: 800

inputs:
  email: "test@example.com"
  phone: "+1234567890"
  username: "testuser"

interactions:
  cookie_banner: dismiss
  modals: close_on_appear
  infinite_scroll: scroll_3_times

tests:
  skip_visual:
    - "/404"
    - "/500"
  custom_assertions: []

api:
  ignore_endpoints:
    - "/api/analytics/*"
    - "/api/tracking/*"
  expected_overrides:
    "GET /api/health":
      status: 200

execution:
  mode: smart
  suites:
    auth-flow:
      mode: sequential
      shared_context: true
    product-pages:
      mode: parallel
      workers: 4
"""


@pytest.mark.unit
class TestRulesConfig:
    def test_parse_from_yaml(self) -> None:
        config = RulesConfig.from_yaml(SAMPLE_YAML)
        assert config.crawl.max_depth == 5
        assert len(config.crawl.skip_urls) == 2
        assert config.inputs.values["email"] == "test@example.com"
        assert config.interactions.cookie_banner == "dismiss"
        assert config.execution.mode == "smart"

    def test_defaults_when_empty(self) -> None:
        config = RulesConfig.from_yaml("")
        assert config.crawl.max_depth == 10
        assert config.crawl.skip_urls == []
        assert config.inputs.values == {}
        assert config.execution.mode == "smart"


@pytest.mark.unit
class TestRulesEngine:
    @pytest.fixture()
    def engine(self) -> RulesEngine:
        config = RulesConfig.from_yaml(SAMPLE_YAML)
        return RulesEngine(config)

    def test_should_skip_url_exact_match(self, engine: RulesEngine) -> None:
        assert engine.should_skip_url("/admin/settings") is True
        assert engine.should_skip_url("/api/internal/users") is True

    def test_should_not_skip_allowed_url(self, engine: RulesEngine) -> None:
        assert engine.should_skip_url("/products") is False
        assert engine.should_skip_url("/api/products") is False

    def test_get_input_value(self, engine: RulesEngine) -> None:
        assert engine.get_input_value("email") == "test@example.com"
        assert engine.get_input_value("phone") == "+1234567890"
        assert engine.get_input_value("nonexistent") is None

    def test_should_skip_visual(self, engine: RulesEngine) -> None:
        assert engine.should_skip_visual("/404") is True
        assert engine.should_skip_visual("/home") is False

    def test_should_ignore_endpoint(self, engine: RulesEngine) -> None:
        assert engine.should_ignore_endpoint("/api/analytics/pageview") is True
        assert engine.should_ignore_endpoint("/api/products") is False

    def test_get_expected_override(self, engine: RulesEngine) -> None:
        override = engine.get_expected_override("GET", "/api/health")
        assert override is not None
        assert override["status"] == 200
        assert engine.get_expected_override("POST", "/api/users") is None

    def test_get_execution_mode(self, engine: RulesEngine) -> None:
        assert engine.get_execution_mode() == "smart"

    def test_get_suite_config(self, engine: RulesEngine) -> None:
        auth = engine.get_suite_config("auth-flow")
        assert auth is not None
        assert auth["mode"] == "sequential"
        assert auth["shared_context"] is True
        assert engine.get_suite_config("nonexistent") is None

    def test_get_cookie_banner_action(self, engine: RulesEngine) -> None:
        assert engine.get_cookie_banner_action() == "dismiss"

    def test_get_modal_action(self, engine: RulesEngine) -> None:
        assert engine.get_modal_action() == "close_on_appear"

    def test_get_scroll_behavior(self, engine: RulesEngine) -> None:
        assert engine.get_scroll_behavior() == "incremental"

    def test_get_infinite_scroll_action(self, engine: RulesEngine) -> None:
        assert engine.get_infinite_scroll_action() == "scroll_3_times"

    def test_get_viewport(self, engine: RulesEngine) -> None:
        vp = engine.get_viewport()
        assert vp == {"width": 1280, "height": 800}

    def test_get_wait_times(self, engine: RulesEngine) -> None:
        wt = engine.get_wait_times()
        assert wt["page_load"] == 3000
        assert wt["after_click"] == 1000

    def test_to_yaml_roundtrip(self, engine: RulesEngine) -> None:
        yaml_str = engine.to_yaml()
        config2 = RulesConfig.from_yaml(yaml_str)
        engine2 = RulesEngine(config2)
        assert engine2.should_skip_url("/admin/settings") is True
        assert engine2.get_input_value("email") == "test@example.com"
