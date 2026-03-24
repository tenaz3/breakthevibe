"""Tests for test case caching — repository round-trip and domain model fidelity."""

import pytest

from breakthevibe.models.domain import GeneratedTestCase, ResilientSelector, TestStep
from breakthevibe.types import SelectorStrategy, TestCategory


@pytest.mark.unit
class TestGeneratedTestCaseRoundTrip:
    """Verify that GeneratedTestCase survives JSON serialization for caching."""

    def _make_case(self) -> GeneratedTestCase:
        return GeneratedTestCase(
            name="test_login_flow",
            category=TestCategory.FUNCTIONAL,
            description="Verify login redirects to dashboard",
            route="/login",
            steps=[
                TestStep(
                    action="navigate",
                    target_url="/login",
                    description="Go to login page",
                ),
                TestStep(
                    action="fill",
                    selectors=[
                        ResilientSelector(
                            strategy=SelectorStrategy.TEST_ID,
                            value="email-input",
                        ),
                        ResilientSelector(
                            strategy=SelectorStrategy.ROLE,
                            value="textbox",
                            name="Email",
                        ),
                    ],
                    expected="user@example.com",
                    description="Fill email field",
                ),
                TestStep(
                    action="click",
                    selectors=[
                        ResilientSelector(
                            strategy=SelectorStrategy.ROLE,
                            value="button",
                            name="Sign in",
                        ),
                    ],
                    description="Click sign in button",
                ),
                TestStep(
                    action="assert_url",
                    expected="/dashboard",
                    description="Verify redirect to dashboard",
                ),
            ],
            code="async def test_login_flow(page): ...",
        )

    def test_steps_serialize_to_json(self) -> None:
        """Steps can be serialized to JSON dicts."""
        import json

        case = self._make_case()
        steps_data = json.dumps([step.model_dump() for step in case.steps], default=str)
        parsed = json.loads(steps_data)
        assert len(parsed) == 4
        assert parsed[0]["action"] == "navigate"
        assert parsed[1]["selectors"][0]["strategy"] == "test_id"
        assert parsed[1]["selectors"][1]["name"] == "Email"

    def test_steps_deserialize_from_json(self) -> None:
        """Steps can be reconstructed from JSON dicts."""
        import json

        case = self._make_case()
        steps_data = json.dumps([step.model_dump() for step in case.steps], default=str)
        parsed = json.loads(steps_data)
        restored = [TestStep.model_validate(s) for s in parsed]
        assert len(restored) == 4
        assert restored[0].action == "navigate"
        assert restored[0].target_url == "/login"
        assert restored[1].selectors[0].strategy == SelectorStrategy.TEST_ID
        assert restored[1].selectors[0].value == "email-input"
        assert restored[1].selectors[1].name == "Email"
        assert restored[2].selectors[0].name == "Sign in"
        assert restored[3].expected == "/dashboard"

    def test_full_case_round_trip(self) -> None:
        """Full GeneratedTestCase survives serialize -> deserialize."""
        import json

        original = self._make_case()
        # Simulate what TestCaseRepository does
        steps_json = json.dumps([s.model_dump() for s in original.steps], default=str)
        parsed_steps = json.loads(steps_json)
        restored = GeneratedTestCase(
            name=original.name,
            category=TestCategory(original.category.value),
            description=original.description,
            route=original.route,
            steps=[TestStep.model_validate(s) for s in parsed_steps],
            code=original.code,
        )
        assert restored.name == original.name
        assert restored.category == original.category
        assert restored.description == original.description
        assert restored.route == original.route
        assert len(restored.steps) == len(original.steps)
        assert restored.code == original.code
        # Deep check selector fidelity
        assert restored.steps[1].selectors[0].value == "email-input"
        assert restored.steps[1].selectors[1].name == "Email"

    def test_empty_steps_round_trip(self) -> None:
        """Case with no steps survives round-trip."""
        import json

        case = GeneratedTestCase(
            name="test_empty",
            category=TestCategory.API,
            description="Empty test",
            route="/",
            steps=[],
        )
        steps_json = json.dumps([s.model_dump() for s in case.steps], default=str)
        assert json.loads(steps_json) == []
