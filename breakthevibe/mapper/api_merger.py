"""Merges observed API traffic with OpenAPI spec definitions."""

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import structlog

from breakthevibe.models.domain import ApiCallInfo

logger = structlog.get_logger(__name__)


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
        matched_spec_keys: set[str] = set()
        matched: list[ApiCallInfo] = []
        traffic_only: list[ApiCallInfo] = []

        for call in traffic:
            path = urlparse(call.url).path
            method = call.method.lower()

            # Try exact match first, then parameterized path matching
            spec_key = self._find_matching_spec(method, path, spec_endpoints)
            if spec_key:
                matched.append(call)
                matched_spec_keys.add(spec_key)
            else:
                traffic_only.append(call)

        spec_only = [
            {"path": ep["path"], "method": ep["method"], "summary": ep.get("summary", "")}
            for key, ep in spec_endpoints.items()
            if key not in matched_spec_keys
        ]

        if traffic_only or spec_only:
            logger.warning(
                "api_merge_mismatches",
                traffic_only=len(traffic_only),
                spec_only=len(spec_only),
            )

        return MergeResult(matched=matched, traffic_only=traffic_only, spec_only=spec_only)

    def _find_matching_spec(
        self,
        method: str,
        path: str,
        spec_endpoints: dict[str, dict[str, Any]],
    ) -> str | None:
        """Find a matching spec endpoint, supporting parameterized paths like /users/{id}."""
        # Exact match
        exact_key = f"{method}:{path}"
        if exact_key in spec_endpoints:
            return exact_key

        # Parameterized match: convert /users/{id} to regex /users/[^/]+
        for key, ep in spec_endpoints.items():
            if not key.startswith(f"{method}:"):
                continue
            spec_path = ep["path"]
            if "{" not in spec_path:
                continue
            # Convert {param} placeholders to regex groups
            pattern = re.sub(r"\{[^}]+\}", r"[^/]+", re.escape(spec_path))
            pattern = pattern.replace(r"\[^/\]\+", "[^/]+")  # unescape our replacements
            if re.fullmatch(pattern, path):
                return key

        return None

    def _extract_spec_endpoints(self, spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Extract path+method pairs from OpenAPI spec."""
        endpoints: dict[str, dict[str, Any]] = {}
        paths = spec.get("paths", {})
        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, details in methods.items():
                if method.lower() in ("get", "post", "put", "patch", "delete"):
                    key = f"{method.lower()}:{path}"
                    endpoints[key] = {
                        "path": path,
                        "method": method.lower(),
                        "summary": details.get("summary", "") if isinstance(details, dict) else "",
                    }
        return endpoints
