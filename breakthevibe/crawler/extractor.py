"""Component and interaction extraction from page DOM."""

from typing import Any

from playwright.async_api import Page

from breakthevibe.models.domain import ComponentInfo, InteractionInfo, ResilientSelector
from breakthevibe.types import SelectorStrategy

# JavaScript to extract interactive and structural elements from the DOM
EXTRACT_JS = """
() => {
    const elements = [];
    const selectors = 'a, button, input, select, textarea, [role], nav, form, '
        + 'header, footer, main, aside, [data-testid], [data-test]';
    document.querySelectorAll(selectors).forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;
        const interactive = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName);

        // Build structural path (for STRUCTURAL selector)
        const path = [];
        let node = el;
        while (node && node !== document.body) {
            let seg = node.tagName.toLowerCase();
            if (node.id) { seg += '#' + node.id; }
            path.unshift(seg);
            node = node.parentElement;
        }

        // Semantic tag detection (for SEMANTIC selector)
        const semanticTags = ['nav', 'header', 'footer', 'main', 'aside', 'article',
                              'section', 'form', 'table', 'figure', 'dialog'];
        let semanticContext = null;
        let parent = el.closest(semanticTags.join(','));
        if (parent) {
            semanticContext = parent.tagName.toLowerCase()
                + (parent.getAttribute('aria-label')
                    ? '[' + parent.getAttribute('aria-label') + ']' : '');
        }

        elements.push({
            tag: el.tagName.toLowerCase(),
            text: (el.textContent || '').trim().slice(0, 200),
            aria_role: el.getAttribute('role') || el.tagName.toLowerCase(),
            is_interactive: interactive,
            test_id: el.getAttribute('data-testid') || el.getAttribute('data-test'),
            css_selector: el.tagName.toLowerCase()
                + (el.id ? '#' + el.id : '')
                + (el.className ? '.' + [...el.classList].join('.') : ''),
            aria_name: el.getAttribute('aria-label') || el.getAttribute('name') || null,
            bounding_box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
            visible: rect.width > 0 && rect.height > 0,
            structural_path: path.join(' > '),
            semantic_context: semanticContext,
        });
    });
    return elements;
}
"""


class ComponentExtractor:
    """Extracts components and interactions from a Playwright page."""

    async def extract_components(self, page: Page) -> list[ComponentInfo]:
        """Extract all meaningful components via DOM analysis + accessibility snapshot (#15)."""
        # Playwright accessibility tree for richer semantic structure
        try:
            self._a11y_snapshot = await page.accessibility.snapshot()  # type: ignore[union-attr]
        except Exception:
            self._a11y_snapshot = None

        raw_elements: list[dict[str, Any]] = await page.evaluate(EXTRACT_JS)

        # Build a11y lookup for enrichment: maps name -> a11y node properties
        a11y_lookup = self._build_a11y_lookup(self._a11y_snapshot) if self._a11y_snapshot else {}

        components = []
        for el in raw_elements:
            if not el.get("visible", False):
                continue
            selectors = self._build_selectors(el)

            # Enrich from accessibility tree: pick up refined role/name/state
            aria_role = el.get("aria_role")
            aria_name = el.get("aria_name")
            name_key = aria_name or el.get("text", "")[:50]
            a11y_node = a11y_lookup.get(name_key)
            if a11y_node:
                aria_role = a11y_node.get("role", aria_role)
                if not aria_name and a11y_node.get("name"):
                    aria_name = a11y_node["name"]

            components.append(
                ComponentInfo(
                    name=aria_name or el.get("text", "")[:50] or el["tag"],
                    element_type=el["tag"],
                    selectors=selectors,
                    text_content=el.get("text") or None,
                    aria_role=aria_role,
                    aria_name=aria_name,
                    test_id=el.get("test_id"),
                    is_interactive=el.get("is_interactive", False),
                    visible=el.get("visible", True),
                    bounding_box=el.get("bounding_box"),
                )
            )
        return components

    async def extract_interactions(self, page: Page) -> list[InteractionInfo]:
        """Extract interactive elements as interactions."""
        raw_elements: list[dict[str, Any]] = await page.evaluate(EXTRACT_JS)
        interactions = []
        for el in raw_elements:
            if not el.get("visible") or not el.get("is_interactive"):
                continue
            action_type = self._infer_action_type(el["tag"])
            selectors = self._build_selectors(el)
            interactions.append(
                InteractionInfo(
                    name=el.get("aria_name") or el.get("text", "")[:50] or el["tag"],
                    action_type=action_type,
                    component_name=el.get("aria_name") or el["tag"],
                    selectors=selectors,
                )
            )
        return interactions

    async def take_screenshot(self, page: Page, path: str) -> bytes:
        """Take a full-page screenshot."""
        kwargs: dict[str, Any] = {"full_page": True}
        if path:
            kwargs["path"] = path
        return await page.screenshot(**kwargs)

    def _build_selectors(self, el: dict[str, Any]) -> list[ResilientSelector]:
        """Build ordered list of selectors from most to least stable."""
        selectors: list[ResilientSelector] = []
        if el.get("test_id"):
            selectors.append(
                ResilientSelector(strategy=SelectorStrategy.TEST_ID, value=el["test_id"])
            )
        if el.get("aria_role") and el.get("aria_name"):
            selectors.append(
                ResilientSelector(
                    strategy=SelectorStrategy.ROLE,
                    value=el["aria_role"],
                    name=el["aria_name"],
                )
            )
        if el.get("text") and len(el["text"]) < 100:
            selectors.append(
                ResilientSelector(strategy=SelectorStrategy.TEXT, value=el["text"][:100])
            )
        # SEMANTIC: use semantic HTML context
        if el.get("semantic_context"):
            selectors.append(
                ResilientSelector(strategy=SelectorStrategy.SEMANTIC, value=el["semantic_context"])
            )
        # STRUCTURAL: use DOM path
        if el.get("structural_path"):
            selectors.append(
                ResilientSelector(strategy=SelectorStrategy.STRUCTURAL, value=el["structural_path"])
            )
        if el.get("css_selector"):
            selectors.append(
                ResilientSelector(strategy=SelectorStrategy.CSS, value=el["css_selector"])
            )
        return selectors

    def _build_a11y_lookup(self, snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Flatten the accessibility tree into a name -> node lookup for enrichment."""
        lookup: dict[str, dict[str, Any]] = {}
        self._walk_a11y_tree(snapshot, lookup)
        return lookup

    def _walk_a11y_tree(self, node: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> None:
        """Recursively walk a11y snapshot nodes."""
        name = node.get("name", "")
        if name:
            lookup[name] = {
                "role": node.get("role"),
                "name": name,
                "value": node.get("value"),
            }
        for child in node.get("children", []):
            self._walk_a11y_tree(child, lookup)

    def _infer_action_type(self, tag: str) -> str:
        """Infer interaction type from element tag."""
        tag_actions = {
            "button": "click",
            "a": "click",
            "input": "input",
            "textarea": "input",
            "select": "select",
        }
        return tag_actions.get(tag, "click")
