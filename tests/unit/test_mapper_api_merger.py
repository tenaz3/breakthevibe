import pytest

from breakthevibe.mapper.api_merger import ApiMerger
from breakthevibe.models.domain import ApiCallInfo

OBSERVED_TRAFFIC = [
    ApiCallInfo(url="https://example.com/api/users", method="GET", status_code=200),
    ApiCallInfo(url="https://example.com/api/products", method="GET", status_code=200),
    ApiCallInfo(url="https://example.com/api/products", method="POST", status_code=201),
]

OPENAPI_SPEC = {
    "openapi": "3.0.0",
    "paths": {
        "/api/users": {
            "get": {"summary": "List users", "responses": {"200": {}}},
        },
        "/api/products": {
            "get": {"summary": "List products", "responses": {"200": {}}},
            "post": {"summary": "Create product", "responses": {"201": {}}},
        },
        "/api/orders": {
            "get": {"summary": "List orders", "responses": {"200": {}}},
        },
    },
}


@pytest.mark.unit
class TestApiMerger:
    def test_merge_finds_all_observed(self) -> None:
        merger = ApiMerger()
        result = merger.merge(OBSERVED_TRAFFIC, OPENAPI_SPEC)
        assert len(result.matched) == 3

    def test_merge_detects_unobserved_spec_endpoints(self) -> None:
        merger = ApiMerger()
        result = merger.merge(OBSERVED_TRAFFIC, OPENAPI_SPEC)
        assert len(result.spec_only) == 1
        assert result.spec_only[0]["path"] == "/api/orders"
        assert result.spec_only[0]["method"] == "get"

    def test_merge_detects_traffic_not_in_spec(self) -> None:
        extra_traffic = [
            *OBSERVED_TRAFFIC,
            ApiCallInfo(
                url="https://example.com/api/internal/health", method="GET", status_code=200
            ),
        ]
        merger = ApiMerger()
        result = merger.merge(extra_traffic, OPENAPI_SPEC)
        assert len(result.traffic_only) == 1
        assert "/api/internal/health" in result.traffic_only[0].url

    def test_merge_without_spec(self) -> None:
        merger = ApiMerger()
        result = merger.merge(OBSERVED_TRAFFIC, None)
        assert len(result.matched) == 0
        assert len(result.traffic_only) == 3
        assert len(result.spec_only) == 0

    def test_merge_empty_traffic(self) -> None:
        merger = ApiMerger()
        result = merger.merge([], OPENAPI_SPEC)
        assert len(result.matched) == 0
        assert len(result.spec_only) == 4
