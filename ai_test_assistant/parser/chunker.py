"""Converts parsed OpenAPI specifications into discrete, retrievable EndpointChunks."""

from typing import Any, Dict, List, Optional

from ai_test_assistant.parser.models import (
    EndpointChunk,
    HTTPMethod,
    ParameterLocation,
    ParameterSpec,
    RequestBodySpec,
    ResponseSpec,
)
from ai_test_assistant.parser.spec_parser import SpecParser


class EndpointChunker:
    """Chunks an OpenAPI specification into granular, self-contained endpoint objects."""

    VALID_METHODS = {m.value.lower() for m in HTTPMethod}

    def __init__(self, parser: SpecParser):
        self.parser = parser

    def chunk_all(self) -> List[EndpointChunk]:
        """Process all paths in the specification into EndpointChunk instances."""
        chunks: List[EndpointChunk] = []
        paths = self.parser.paths

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            # Shared path-level parameters
            path_level_params = path_item.get("parameters", [])

            for method_key, operation in path_item.items():
                if method_key.lower() not in self.VALID_METHODS:
                    continue

                if not isinstance(operation, dict):
                    continue

                chunk = self._build_chunk(
                    path=path,
                    method_str=method_key.upper(),
                    operation=operation,
                    path_level_params=path_level_params,
                )
                chunks.append(chunk)

        return chunks

    def _build_chunk(
        self,
        path: str,
        method_str: str,
        operation: Dict[str, Any],
        path_level_params: List[Any],
    ) -> EndpointChunk:
        """Construct an individual EndpointChunk from operation details."""
        method = HTTPMethod(method_str)
        operation_id = operation.get("operationId")
        summary = operation.get("summary", "")
        description = operation.get("description", "")
        tags = operation.get("tags", [])
        chunk_id = operation_id or f"{method.value}_{path.replace('/', '_').strip('_')}"

        # 1. Parse Parameters (combining path-level and operation-level)
        op_params = operation.get("parameters", [])
        all_raw_params = list(path_level_params) + list(op_params)
        parameters = self._parse_parameters(all_raw_params)

        # 2. Parse Request Body
        request_body = self._parse_request_body(operation, all_raw_params)

        # 3. Parse Responses
        responses = self._parse_responses(operation.get("responses", {}))

        # 4. Parse Security
        security = self._parse_security(operation)

        return EndpointChunk(
            chunk_id=chunk_id,
            method=method,
            path=path,
            summary=summary,
            description=description,
            operation_id=operation_id,
            parameters=parameters,
            request_body=request_body,
            responses=responses,
            security=security,
            tags=tags,
        )

    def _parse_parameters(self, raw_params: List[Any]) -> List[ParameterSpec]:
        """Parse parameter definitions, resolving $refs if present."""
        seen_keys = set()
        param_specs: List[ParameterSpec] = []

        for p in raw_params:
            if not isinstance(p, dict):
                continue

            # Resolve parameter $ref if necessary
            if "$ref" in p:
                p = self.parser.resolve_ref(p["$ref"])
                if not isinstance(p, dict):
                    continue

            name = p.get("name", "")
            location_str = p.get("in", "query").lower()
            if not name or location_str not in {"query", "path", "header", "cookie"}:
                continue

            # Deduplicate by (name, in)
            key = (name, location_str)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            location = ParameterLocation(location_str)
            required = p.get("required", location == ParameterLocation.PATH)
            description = p.get("description", "")

            # Schema handling (OpenAPI 3 uses schema object, Swagger 2 uses top-level type)
            schema = p.get("schema", {})
            if "$ref" in schema:
                schema = self.parser.resolve_schema(schema)

            schema_type = schema.get("type", p.get("type", "string"))
            default = schema.get("default", p.get("default"))
            enum_values = schema.get("enum", p.get("enum"))

            param_specs.append(
                ParameterSpec(
                    name=name,
                    location=location,
                    required=required,
                    schema_type=str(schema_type),
                    description=description,
                    default=default,
                    enum_values=enum_values,
                )
            )

        return param_specs

    def _parse_request_body(
        self, operation: Dict[str, Any], raw_params: List[Any]
    ) -> Optional[RequestBodySpec]:
        """Extract request body definition from OpenAPI 3 requestBody or Swagger 2 body param."""
        # OpenAPI 3.x
        if "requestBody" in operation:
            rb = operation["requestBody"]
            if "$ref" in rb:
                rb = self.parser.resolve_ref(rb["$ref"])

            if not isinstance(rb, dict):
                return None

            content = rb.get("content", {})
            required = rb.get("required", False)

            # Prefer application/json if available
            preferred_ct = "application/json"
            if preferred_ct not in content and content:
                preferred_ct = next(iter(content.keys()))

            ct_info = content.get(preferred_ct, {})
            schema = ct_info.get("schema", {})
            if "$ref" in schema:
                schema = self.parser.resolve_schema(schema)

            example = ct_info.get("example") or schema.get("example")

            return RequestBodySpec(
                content_type=preferred_ct,
                schema_def=schema,
                required=required,
                example=example,
            )

        # Swagger 2.0 (body in parameters)
        for p in raw_params:
            if isinstance(p, dict) and p.get("in") == "body":
                schema = p.get("schema", {})
                if "$ref" in schema:
                    schema = self.parser.resolve_schema(schema)
                return RequestBodySpec(
                    content_type="application/json",
                    schema_def=schema,
                    required=p.get("required", False),
                    example=p.get("example") or schema.get("example"),
                )

        return None

    def _parse_responses(self, raw_responses: Dict[str, Any]) -> Dict[str, ResponseSpec]:
        """Parse status code responses and their schemas."""
        responses: Dict[str, ResponseSpec] = {}

        for code_str, r_data in raw_responses.items():
            if not isinstance(r_data, dict):
                continue

            if "$ref" in r_data:
                r_data = self.parser.resolve_ref(r_data["$ref"])
                if not isinstance(r_data, dict):
                    continue

            desc = r_data.get("description", "")
            headers = r_data.get("headers", {})

            # Schema in OpenAPI 3 is inside content
            schema = None
            if "content" in r_data:
                content = r_data["content"]
                if "application/json" in content:
                    schema = content["application/json"].get("schema")
                elif content:
                    first_ct = next(iter(content.values()))
                    schema = first_ct.get("schema")
            elif "schema" in r_data:  # Swagger 2
                schema = r_data.get("schema")

            if schema and isinstance(schema, dict) and "$ref" in schema:
                schema = self.parser.resolve_schema(schema)

            responses[str(code_str)] = ResponseSpec(
                status_code=str(code_str),
                description=desc,
                schema_def=schema,
                headers=headers,
            )

        return responses

    def _parse_security(self, operation: Dict[str, Any]) -> List[str]:
        """Extract names of required security schemes for the operation."""
        # Operation-level or spec-level
        sec_list = operation.get("security", self.parser.raw_spec.get("security", []))
        sec_names: List[str] = []

        if isinstance(sec_list, list):
            for sec_req in sec_list:
                if isinstance(sec_req, dict):
                    sec_names.extend(sec_req.keys())

        return list(dict.fromkeys(sec_names))
