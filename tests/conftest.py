"""Pytest configuration and shared fixtures for AI Test Assistant test suite."""

from pathlib import Path
import pytest

from ai_test_assistant.parser.chunker import EndpointChunker
from ai_test_assistant.parser.models import EndpointChunk, HTTPMethod
from ai_test_assistant.parser.spec_parser import SpecParser


@pytest.fixture
def petstore_spec_path() -> Path:
    return Path(__file__).parent.parent / "examples" / "specs" / "petstore.json"


@pytest.fixture
def ecommerce_spec_path() -> Path:
    return Path(__file__).parent.parent / "examples" / "specs" / "ecommerce.yaml"


@pytest.fixture
def adversarial_spec_path() -> Path:
    return Path(__file__).parent.parent / "examples" / "specs" / "adversarial_injection.yaml"


@pytest.fixture
def sample_petstore_chunks(petstore_spec_path) -> list[EndpointChunk]:
    parser = SpecParser.from_file(petstore_spec_path)
    chunker = EndpointChunker(parser)
    return chunker.chunk_all()


@pytest.fixture
def dummy_endpoint_chunk() -> EndpointChunk:
    return EndpointChunk(
        chunk_id="get_users",
        method=HTTPMethod.GET,
        path="/api/v1/users",
        summary="List all registered system users",
        description="Returns user accounts with pagination",
        tags=["users"],
    )
