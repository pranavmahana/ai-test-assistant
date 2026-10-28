"""Unit tests for OpenAPI specification parsing and $ref resolution."""

import json
from pathlib import Path
import pytest

from ai_test_assistant.parser.spec_parser import SpecParser


def test_parse_valid_json_file(petstore_spec_path):
    parser = SpecParser.from_file(petstore_spec_path)
    assert parser.version.startswith("3.0")
    assert parser.title == "Swagger Petstore"
    assert parser.base_url == "http://localhost:8000/api/v1"
    assert "/pets" in parser.paths
    assert "/pets/{petId}" in parser.paths


def test_parse_valid_yaml_file(ecommerce_spec_path):
    parser = SpecParser.from_file(ecommerce_spec_path)
    assert parser.version.startswith("3.0")
    assert parser.title == "E-Commerce Store API"
    assert parser.base_url == "https://api.mystore.com/v2"
    assert "/orders" in parser.paths


def test_parse_from_string():
    spec_str = json.dumps({
        "openapi": "3.1.0",
        "info": {"title": "Inline Test API", "version": "1.0"},
        "paths": {"/ping": {"get": {"summary": "Ping"}}}
    })
    parser = SpecParser.from_string(spec_str)
    assert parser.title == "Inline Test API"
    assert "/ping" in parser.paths


def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        SpecParser.from_file("non_existent_spec_file.json")


def test_resolve_ref_local(petstore_spec_path):
    parser = SpecParser.from_file(petstore_spec_path)
    resolved = parser.resolve_ref("#/components/schemas/Pet")
    assert resolved.get("type") == "object"
    assert "id" in resolved.get("properties", {})
    assert "name" in resolved.get("properties", {})


def test_resolve_ref_missing(petstore_spec_path):
    parser = SpecParser.from_file(petstore_spec_path)
    resolved = parser.resolve_ref("#/components/schemas/NonExistent")
    assert resolved == {}


def test_resolve_nested_schema():
    raw = {
        "openapi": "3.0.0",
        "components": {
            "schemas": {
                "Item": {"type": "string"},
                "Container": {"$ref": "#/components/schemas/Item"}
            }
        }
    }
    parser = SpecParser(raw)
    resolved = parser.resolve_schema({"$ref": "#/components/schemas/Container"})
    assert resolved == {"type": "string"}
