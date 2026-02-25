"""Mind-map builder from crawl data."""

import structlog

from breakthevibe.models.domain import ApiCallInfo, CrawlResult, SiteMap

logger = structlog.get_logger(__name__)


class MindMapBuilder:
    """Builds a SiteMap (mind-map) from crawl results."""

    def build(self, crawl: CrawlResult, base_url: str) -> SiteMap:
        """Build a SiteMap from crawl results, deduplicating API endpoints."""
        all_api_calls = self._deduplicate_api_calls(crawl)
        return SiteMap(
            base_url=base_url,
            pages=crawl.pages,
            api_endpoints=all_api_calls,
        )

    def _deduplicate_api_calls(self, crawl: CrawlResult) -> list[ApiCallInfo]:
        """Collect and deduplicate API calls across all pages."""
        seen: set[str] = set()
        unique: list[ApiCallInfo] = []
        for page in crawl.pages:
            for call in page.api_calls:
                key = f"{call.method}:{call.url}"
                if key not in seen:
                    seen.add(key)
                    unique.append(call)
        return unique
