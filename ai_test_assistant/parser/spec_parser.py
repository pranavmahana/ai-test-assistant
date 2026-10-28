"""OpenAPI and Swagger specification parser with JSON/YAML and $ref resolution support."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml


class SpecParser:
    """Parses OpenAPI 3.0/3.1 and Swagger 2.0 specifications from files or raw strings."""

    def __init__(self, raw_spec: Dict[str, Any]):
        self.raw_spec = raw_spec
        self.version = self._detect_version()
        self.title = self.raw_spec.get("info", {}).get("title", "API Specification")
        self.base_url = self._extract_base_url()

    @classmethod
    def from_file(cls, file_path: Union[str, Path]) -> "SpecParser":
        """Load and parse an OpenAPI specification from a JSON or YAML file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenAPI spec file not found: {path}")

        content = path.read_text(encoding="utf-8")
        return cls.from_string(content, is_yaml=(path.suffix.lower() in [".yaml", ".yml"]))

    @classmethod
    def from_string(cls, content: str, is_yaml: Optional[bool] = None) -> "SpecParser":
        """Parse an OpenAPI spec from a string (auto-detects JSON vs YAML if not specified)."""
        content_stripped = content.strip()
        data: Dict[str, Any]

        if is_yaml is True:
            data = yaml.safe_load(content)
        elif is_yaml is False:
            data = json.loads(content)
        else:
            # Auto-detect: if starts with { or [ try json first
            if content_stripped.startswith("{"):
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    data = yaml.safe_load(content)
            else:
                try:
                    data = yaml.safe_load(content)
                except Exception:
                    data = json.loads(content)

        if not isinstance(data, dict):
            raise ValueError("Parsed OpenAPI specification must be a dictionary.")

        return cls(data)

    def _detect_version(self) -> str:
        """Detect the specification version (OpenAPI 3.x vs Swagger 2.0)."""
        if "openapi" in self.raw_spec:
            return str(self.raw_spec["openapi"])
        if "swagger" in self.raw_spec:
            return f"swagger-{self.raw_spec['swagger']}"
        return "unknown"

    def _extract_base_url(self) -> str:
        """Extract the default base URL from the spec."""
        # OpenAPI 3.x: servers array
        servers = self.raw_spec.get("servers", [])
        if servers and isinstance(servers, list) and len(servers) > 0:
            first_url = servers[0].get("url", "")
            if first_url:
                return first_url

        # Swagger 2.0: schemes, host, basePath
        host = self.raw_spec.get("host", "localhost:8000")
        base_path = self.raw_spec.get("basePath", "")
        schemes = self.raw_spec.get("schemes", ["http"])
        scheme = schemes[0] if schemes else "http"
        return f"{scheme}://{host}{base_path}"

    def resolve_ref(self, ref_str: str) -> Any:
        """Resolve a local JSON Pointer $ref (e.g., '#/components/schemas/User')."""
        if not ref_str.startswith("#/"):
            # External references are not resolved offline
            return {}

        parts = ref_str.lstrip("#/").split("/")
        curr: Any = self.raw_spec
        for part in parts:
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                return {}
        return curr

    def resolve_schema(self, schema_or_ref: Any, depth: int = 0) -> Any:
        """Recursively resolve $ref pointers inside schemas up to depth limit."""
        if depth > 10:  # Prevent circular loops
            return schema_or_ref

        if isinstance(schema_or_ref, dict):
            if "$ref" in schema_or_ref and len(schema_or_ref) == 1:
                resolved = self.resolve_ref(schema_or_ref["$ref"])
                return self.resolve_schema(resolved, depth + 1)
            elif "$ref" in schema_or_ref:
                resolved = self.resolve_ref(schema_or_ref["$ref"])
                merged = {**resolved, **schema_or_ref}
                del merged["$ref"]
                return self.resolve_schema(merged, depth + 1)
            else:
                return {k: self.resolve_schema(v, depth + 1) for k, v in schema_or_ref.items()}
        elif isinstance(schema_or_ref, list):
            return [self.resolve_schema(item, depth + 1) for item in schema_or_ref]
        return schema_or_ref

    @property
    def paths(self) -> Dict[str, Any]:
        """Return the raw paths dictionary from the spec."""
        return self.raw_spec.get("paths", {})
