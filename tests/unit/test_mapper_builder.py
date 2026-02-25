import pytest

from breakthevibe.mapper.builder import MindMapBuilder
from breakthevibe.models.domain import (
    ApiCallInfo,
    ComponentInfo,
    CrawlResult,
    InteractionInfo,
    PageData,
    ResilientSelector,
    SiteMap,
)
from breakthevibe.types import SelectorStrategy


def make_page(path: str, components: int = 2, api_calls: int = 1) -> PageData:
    """Helper to create test PageData."""
    return PageData(
        url=f"https://example.com{path}",
        path=path,
        title=f"Page {path}",
        components=[
            ComponentInfo(
                name=f"component-{i}",
                element_type="button",
                selectors=[ResilientSelector(strategy=SelectorStrategy.TEXT, value=f"btn-{i}")],
            )
            for i in range(components)
        ],
        interactions=[
            InteractionInfo(
                name=f"click-{i}",
                action_type="click",
                component_name=f"component-{i}",
            )
            for i in range(components)
        ],
        api_calls=[
            ApiCallInfo(url=f"https://example.com/api/data-{i}", method="GET", status_code=200)
            for i in range(api_calls)
        ],
        navigates_to=["/about"] if path == "/" else [],
    )


@pytest.mark.unit
class TestMindMapBuilder:
    @pytest.mark.asyncio
    async def test_build_from_crawl_result(self) -> None:
        crawl = CrawlResult(
            pages=[make_page("/"), make_page("/about")],
            total_routes=2,
            total_components=4,
            total_api_calls=2,
        )
        builder = MindMapBuilder()
        site_map = await builder.build(crawl, base_url="https://example.com")

        assert isinstance(site_map, SiteMap)
        assert site_map.base_url == "https://example.com"
        assert len(site_map.pages) == 2

    @pytest.mark.asyncio
    async def test_deduplicates_api_endpoints(self) -> None:
        page1 = make_page("/", api_calls=0)
        page1.api_calls = [
            ApiCallInfo(url="https://example.com/api/users", method="GET", status_code=200),
            ApiCallInfo(url="https://example.com/api/products", method="GET", status_code=200),
        ]
        page2 = make_page("/about", api_calls=0)
        page2.api_calls = [
            ApiCallInfo(url="https://example.com/api/users", method="GET", status_code=200),
        ]

        crawl = CrawlResult(pages=[page1, page2], total_routes=2)
        builder = MindMapBuilder()
        site_map = await builder.build(crawl, base_url="https://example.com")

        urls = [ep.url for ep in site_map.api_endpoints]
        assert len(urls) == 2
        assert "https://example.com/api/users" in urls
        assert "https://example.com/api/products" in urls

    @pytest.mark.asyncio
    async def test_empty_crawl_result(self) -> None:
        crawl = CrawlResult(pages=[])
        builder = MindMapBuilder()
        site_map = await builder.build(crawl, base_url="https://example.com")

        assert site_map.pages == []
        assert site_map.api_endpoints == []

    @pytest.mark.asyncio
    async def test_to_json(self) -> None:
        crawl = CrawlResult(pages=[make_page("/")])
        builder = MindMapBuilder()
        site_map = await builder.build(crawl, base_url="https://example.com")
        json_str = site_map.model_dump_json()
        assert "https://example.com" in json_str
