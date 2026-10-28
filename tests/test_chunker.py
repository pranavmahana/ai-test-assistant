"""Unit tests for OpenAPI endpoint chunking."""

from ai_test_assistant.parser.chunker import EndpointChunker
from ai_test_assistant.parser.models import HTTPMethod, ParameterLocation
from ai_test_assistant.parser.spec_parser import SpecParser


def test_chunking_petstore(petstore_spec_path):
    parser = SpecParser.from_file(petstore_spec_path)
    chunker = EndpointChunker(parser)
    chunks = chunker.chunk_all()

    # Petstore has: GET /pets, POST /pets, GET /pets/{petId}, DELETE /pets/{petId}
    assert len(chunks) == 4

    keys = {c.endpoint_key for c in chunks}
    assert "GET /pets" in keys
    assert "POST /pets" in keys
    assert "GET /pets/{petId}" in keys
    assert "DELETE /pets/{petId}" in keys


def test_chunk_parameters(petstore_spec_path):
    parser = SpecParser.from_file(petstore_spec_path)
    chunker = EndpointChunker(parser)
    chunks = chunker.chunk_all()

    get_pet_id_chunk = next(c for c in chunks if c.endpoint_key == "GET /pets/{petId}")
    assert len(get_pet_id_chunk.parameters) == 1
    param = get_pet_id_chunk.parameters[0]
    assert param.name == "petId"
    assert param.location == ParameterLocation.PATH
    assert param.required is True


def test_chunk_request_body(petstore_spec_path):
    parser = SpecParser.from_file(petstore_spec_path)
    chunker = EndpointChunker(parser)
    chunks = chunker.chunk_all()

    post_pets_chunk = next(c for c in chunks if c.endpoint_key == "POST /pets")
    assert post_pets_chunk.request_body is not None
    assert post_pets_chunk.request_body.required is True
    assert post_pets_chunk.request_body.content_type == "application/json"
    assert post_pets_chunk.request_body.example == {"name": "Fluffy", "tag": "dog"}


def test_chunk_responses(petstore_spec_path):
    parser = SpecParser.from_file(petstore_spec_path)
    chunker = EndpointChunker(parser)
    chunks = chunker.chunk_all()

    delete_chunk = next(c for c in chunks if c.endpoint_key == "DELETE /pets/{petId}")
    assert "204" in delete_chunk.responses
    assert "404" in delete_chunk.responses


def test_to_search_document(sample_petstore_chunks):
    chunk = sample_petstore_chunks[0]
    doc = chunk.to_search_document()
    assert isinstance(doc, str)
    assert chunk.method.value in doc
    assert "pets" in doc.lower()


def test_to_prompt_chunk_sanitized(sample_petstore_chunks):
    chunk = sample_petstore_chunks[0]
    prompt_chunk = chunk.to_prompt_chunk(sanitize=True)
    assert "<untrusted_spec_data>" in prompt_chunk
    assert "</untrusted_spec_data>" in prompt_chunk
    assert chunk.endpoint_key in prompt_chunk
