import pytest

from breakthevibe.generator.selector import SelectorBuilder
from breakthevibe.models.domain import ComponentInfo, ResilientSelector
from breakthevibe.types import SelectorStrategy


@pytest.mark.unit
class TestSelectorBuilder:
    @pytest.fixture()
    def builder(self) -> SelectorBuilder:
        return SelectorBuilder()

    def test_builds_ordered_selector_chain(self, builder: SelectorBuilder) -> None:
        component = ComponentInfo(
            name="Add to Cart",
            element_type="button",
            selectors=[
                ResilientSelector(strategy=SelectorStrategy.CSS, value=".btn-primary"),
                ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="add-to-cart-btn"),
                ResilientSelector(strategy=SelectorStrategy.TEXT, value="Add to Cart"),
                ResilientSelector(
                    strategy=SelectorStrategy.ROLE, value="button", name="Add to Cart"
                ),
            ],
            aria_role="button",
            text_content="Add to Cart",
        )
        chain = builder.build_chain(component)
        # Should be ordered: test_id first (most stable), then role, text, css
        strategies = [s.strategy for s in chain]
        assert strategies[0] == SelectorStrategy.TEST_ID
        assert strategies[1] == SelectorStrategy.ROLE
        assert strategies[2] == SelectorStrategy.TEXT
        assert strategies[-1] == SelectorStrategy.CSS

    def test_deduplicates_selectors(self, builder: SelectorBuilder) -> None:
        component = ComponentInfo(
            name="Button",
            element_type="button",
            selectors=[
                ResilientSelector(strategy=SelectorStrategy.TEXT, value="Click"),
                ResilientSelector(strategy=SelectorStrategy.TEXT, value="Click"),
                ResilientSelector(strategy=SelectorStrategy.CSS, value=".btn"),
            ],
        )
        chain = builder.build_chain(component)
        text_selectors = [s for s in chain if s.strategy == SelectorStrategy.TEXT]
        assert len(text_selectors) == 1

    def test_empty_selectors_returns_empty(self, builder: SelectorBuilder) -> None:
        component = ComponentInfo(
            name="Empty",
            element_type="div",
            selectors=[],
        )
        chain = builder.build_chain(component)
        assert chain == []

    def test_infers_selectors_from_metadata(self, builder: SelectorBuilder) -> None:
        """When component has metadata but few explicit selectors, infer extras."""
        component = ComponentInfo(
            name="Submit",
            element_type="button",
            selectors=[
                ResilientSelector(strategy=SelectorStrategy.CSS, value="form .submit-btn"),
            ],
            aria_role="button",
            text_content="Submit",
            test_id="submit-btn",
        )
        chain = builder.build_chain(component)
        strategies = [s.strategy for s in chain]
        # Should have inferred test_id, role, and text from metadata
        assert SelectorStrategy.TEST_ID in strategies
        assert SelectorStrategy.ROLE in strategies
        assert SelectorStrategy.TEXT in strategies
        assert SelectorStrategy.CSS in strategies

    def test_priority_order_is_correct(self, builder: SelectorBuilder) -> None:
        """Verify the full priority order: test_id > role > text > semantic > structural > css."""
        component = ComponentInfo(
            name="Link",
            element_type="a",
            selectors=[
                ResilientSelector(strategy=SelectorStrategy.CSS, value="a.nav-link"),
                ResilientSelector(
                    strategy=SelectorStrategy.STRUCTURAL,
                    value="nav > ul > li:nth-child(2) > a",
                ),
                ResilientSelector(strategy=SelectorStrategy.SEMANTIC, value="nav a[href='/about']"),
                ResilientSelector(strategy=SelectorStrategy.TEXT, value="About"),
                ResilientSelector(strategy=SelectorStrategy.ROLE, value="link", name="About"),
                ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="about-link"),
            ],
        )
        chain = builder.build_chain(component)
        strategies = [s.strategy for s in chain]
        assert strategies == [
            SelectorStrategy.TEST_ID,
            SelectorStrategy.ROLE,
            SelectorStrategy.TEXT,
            SelectorStrategy.SEMANTIC,
            SelectorStrategy.STRUCTURAL,
            SelectorStrategy.CSS,
        ]
