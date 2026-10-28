"""Data models for OpenAPI endpoint chunks and specifications."""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ai_test_assistant.security.sanitizer import SpecSanitizer


class HTTPMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"


class ParameterLocation(str, Enum):
    QUERY = "query"
    PATH = "path"
    HEADER = "header"
    COOKIE = "cookie"


@dataclass
class ParameterSpec:
    """Represents a single query, path, header, or cookie parameter."""
    name: str
    location: ParameterLocation
    required: bool = False
    schema_type: str = "string"
    description: str = ""
    default: Optional[Any] = None
    enum_values: Optional[List[Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "in": self.location.value,
            "required": self.required,
            "type": self.schema_type,
            "description": self.description,
            "default": self.default,
            "enum": self.enum_values,
        }


@dataclass
class RequestBodySpec:
    """Represents the request body definition of an operation."""
    content_type: str = "application/json"
    schema_def: Dict[str, Any] = field(default_factory=dict)
    required: bool = False
    example: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_type": self.content_type,
            "required": self.required,
            "schema": self.schema_def,
            "example": self.example,
        }


@dataclass
class ResponseSpec:
    """Represents an expected HTTP response from an endpoint."""
    status_code: str
    description: str = ""
    schema_def: Optional[Dict[str, Any]] = None
    headers: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status_code": self.status_code,
            "description": self.description,
            "schema": self.schema_def,
            "headers": self.headers,
        }


@dataclass
class EndpointChunk:
    """Structured, retrievable chunk representing a single API endpoint operation."""
    chunk_id: str
    method: HTTPMethod
    path: str
    summary: str = ""
    description: str = ""
    operation_id: Optional[str] = None
    parameters: List[ParameterSpec] = field(default_factory=list)
    request_body: Optional[RequestBodySpec] = None
    responses: Dict[str, ResponseSpec] = field(default_factory=dict)
    security: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    @property
    def endpoint_key(self) -> str:
        """Normalized identifier: METHOD /path (e.g., 'POST /api/v1/users')."""
        return f"{self.method.value.upper()} {self.path}"

    def to_search_document(self) -> str:
        """Build a dense text document optimized for TF-IDF tokenization and lexical retrieval."""
        tokens: List[str] = [
            self.method.value,
            self.path,
            # Path segments broken into tokens (e.g., /api/v1/pet-store -> api, v1, pet, store)
            self.path.replace("/", " ").replace("-", " ").replace("_", " "),
            self.summary,
            self.description,
            self.operation_id or "",
            " ".join(self.tags),
        ]

        # Append parameter names and descriptions
        for p in self.parameters:
            tokens.append(f"{p.name} {p.schema_type} {p.location.value} {p.description}")

        # Append request body properties
        if self.request_body and isinstance(self.request_body.schema_def, dict):
            props = self.request_body.schema_def.get("properties", {})
            tokens.extend(props.keys())

        # Append response status codes
        for code, resp in self.responses.items():
            tokens.append(f"{code} {resp.description}")

        return " ".join(t for t in tokens if t)

    def to_prompt_chunk(self, sanitize: bool = True) -> str:
        """Build a structured text chunk for LLM prompts with untrusted data isolation."""
        summary = SpecSanitizer.sanitize_text(self.summary) if sanitize else self.summary
        description = SpecSanitizer.sanitize_text(self.description) if sanitize else self.description

        lines = [
            f"### Endpoint: `{self.method.value} {self.path}`",
            f"- **Operation ID**: `{self.operation_id or 'none'}`",
            f"- **Tags**: {', '.join(self.tags) if self.tags else 'none'}",
            f"- **Security Requirements**: {', '.join(self.security) if self.security else 'None (Public)'}",
            f"- **Summary** [UNTRUSTED]: {summary or 'N/A'}",
            f"- **Description** [UNTRUSTED]: {description or 'N/A'}",
        ]

        if self.parameters:
            lines.append("- **Parameters**:")
            for p in self.parameters:
                p_desc = SpecSanitizer.sanitize_text(p.description) if sanitize else p.description
                req_str = "required" if p.required else "optional"
                lines.append(
                    f"  * `{p.name}` ({p.location.value}, {p.schema_type}, {req_str}): {p_desc or 'no description'}"
                )

        if self.request_body:
            lines.append("- **Request Body**:")
            lines.append(f"  * Content-Type: `{self.request_body.content_type}`")
            lines.append(f"  * Required: `{self.request_body.required}`")
            schema_json = json.dumps(self.request_body.schema_def, indent=2)
            lines.append(f"  * Schema:\n```json\n{schema_json}\n```")
            if self.request_body.example:
                ex_json = json.dumps(self.request_body.example, indent=2)
                lines.append(f"  * Example Payload:\n```json\n{ex_json}\n```")

        if self.responses:
            lines.append("- **Documented Responses**:")
            for code, resp in self.responses.items():
                r_desc = SpecSanitizer.sanitize_text(resp.description) if sanitize else resp.description
                lines.append(f"  * HTTP {code}: {r_desc}")
                if resp.schema_def:
                    schema_json = json.dumps(resp.schema_def, indent=2)
                    lines.append(f"    Schema:\n```json\n{schema_json}\n```")

        content = "\n".join(lines)
        return SpecSanitizer.wrap_untrusted(content, label=self.endpoint_key)
