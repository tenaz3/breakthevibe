"""Merges observed API traffic with OpenAPI spec definitions."""

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from breakthevibe.models.domain import ApiCallInfo


@dataclass
class MergeResult:
    """Result of merging traffic with spec."""

    matched: list[ApiCallInfo] = field(default_factory=list)
    traffic_only: list[ApiCallInfo] = field(default_factory=list)
    spec_only: list[dict[str, Any]] = field(default_factory=list)


class ApiMerger:
    """Merges observed API traffic with OpenAPI/Swagger specification."""

    def merge(self, traffic: list[ApiCallInfo], spec: dict[str, Any] | None) -> MergeResult:
        """Merge observed traffic with OpenAPI spec."""
        if not spec:
            return MergeResult(traffic_only=list(traffic))

        spec_endpoints = self._extract_spec_endpoints(spec)
        traffic_keys: set[str] = set()
        matched: list[ApiCallInfo] = []
        traffic_only: list[ApiCallInfo] = []

        for call in traffic:
            path = urlparse(call.url).path
            key = f"{call.method.lower()}:{path}"
            traffic_keys.add(key)
            if key in spec_endpoints:
                matched.append(call)
            else:
                traffic_only.append(call)

        spec_only = [
            {"path": ep["path"], "method": ep["method"], "summary": ep.get("summary", "")}
            for key, ep in spec_endpoints.items()
            if key not in traffic_keys
        ]

        return MergeResult(matched=matched, traffic_only=traffic_only, spec_only=spec_only)

    def _extract_spec_endpoints(self, spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Extract path+method pairs from OpenAPI spec."""
        endpoints: dict[str, dict[str, Any]] = {}
        paths = spec.get("paths", {})
        for path, methods in paths.items():
            for method, details in methods.items():
                if method.lower() in ("get", "post", "put", "patch", "delete"):
                    key = f"{method.lower()}:{path}"
                    endpoints[key] = {
                        "path": path,
                        "method": method.lower(),
                        "summary": details.get("summary", ""),
                    }
        return endpoints
