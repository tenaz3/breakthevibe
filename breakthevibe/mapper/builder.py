"""Mind-map builder from crawl data."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from breakthevibe.mapper.api_merger import ApiMerger
from breakthevibe.models.domain import (
    ApiCallInfo,
    ApiMergeResult,
    CrawlResult,
    RouteRelationship,
    SiteMap,
)

if TYPE_CHECKING:
    from breakthevibe.mapper.classifier import ComponentClassifier

logger = structlog.get_logger(__name__)


class MindMapBuilder:
    """Builds a SiteMap (mind-map) from crawl results.

    Optionally uses LLM classification and OpenAPI spec merging when
    a classifier and/or merger are provided.
    """

    def __init__(
        self,
        classifier: ComponentClassifier | None = None,
        api_merger: ApiMerger | None = None,
    ) -> None:
        self._classifier = classifier
        self._api_merger = api_merger or ApiMerger()

    async def build(
        self,
        crawl: CrawlResult,
        base_url: str,
        openapi_spec: dict[str, Any] | None = None,
    ) -> SiteMap:
        """Build a SiteMap from crawl results.

        - Deduplicates API endpoints across pages
        - Classifies components via LLM (if classifier provided)
        - Merges observed traffic with OpenAPI spec (if provided)
        """
        # LLM classification of components per page
        if self._classifier:
            for page in crawl.pages:
                if page.components:
                    groups = await self._classifier.classify(page.components, page.url)
                    page.component_groups = groups
                    logger.debug("page_classified", url=page.url, groups=len(groups))

        all_api_calls = self._deduplicate_api_calls(crawl)

        # Build route relationship graph from navigates_to data
        route_relationships = self._build_route_relationships(crawl)

        # Merge with OpenAPI spec if available
        api_merge = None
        if openapi_spec:
            merge_result = self._api_merger.merge(all_api_calls, openapi_spec)
            api_merge = ApiMergeResult(
                matched=merge_result.matched,
                traffic_only=merge_result.traffic_only,
                spec_only=merge_result.spec_only,
            )
            logger.info(
                "api_merge_complete",
                matched=len(merge_result.matched),
                traffic_only=len(merge_result.traffic_only),
                spec_only=len(merge_result.spec_only),
            )

        return SiteMap(
            base_url=base_url,
            pages=crawl.pages,
            api_endpoints=all_api_calls,
            api_merge=api_merge,
            route_relationships=route_relationships,
        )

    def _build_route_relationships(self, crawl: CrawlResult) -> list[RouteRelationship]:
        """Build inter-route navigation graph from page navigates_to data."""
        known_paths = {page.path for page in crawl.pages}
        relationships: list[RouteRelationship] = []
        seen: set[tuple[str, str]] = set()
        for page in crawl.pages:
            for target_path in page.navigates_to:
                if target_path in known_paths and target_path != page.path:
                    key = (page.path, target_path)
                    if key not in seen:
                        seen.add(key)
                        relationships.append(
                            RouteRelationship(
                                source=page.path,
                                target=target_path,
                                relationship="navigates_to",
                            )
                        )
        logger.debug("route_relationships_built", count=len(relationships))
        return relationships

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
