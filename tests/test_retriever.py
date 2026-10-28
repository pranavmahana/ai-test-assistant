"""Unit tests for TF-IDF endpoint retrieval."""

from ai_test_assistant.parser.models import HTTPMethod
from ai_test_assistant.retrieval.tfidf_retriever import (
    TfidfRetriever,
    custom_endpoint_tokenizer,
)


def test_custom_endpoint_tokenizer():
    tokens = custom_endpoint_tokenizer("/api/v1/user-profiles/{userId}")
    assert "api" in tokens
    assert "v1" in tokens
    assert "user" in tokens
    assert "profiles" in tokens
    assert "user" in tokens
    assert "id" in tokens


def test_retriever_query(sample_petstore_chunks):
    retriever = TfidfRetriever(sample_petstore_chunks)
    results = retriever.retrieve(query="create new pet in store", top_k=2)

    assert len(results) > 0
    top = results[0]
    # Creating pet is POST /pets
    assert top.chunk.method == HTTPMethod.POST
    assert top.chunk.path == "/pets"
    assert top.score > 0.0
    assert top.rank == 1


def test_retriever_method_filter(sample_petstore_chunks):
    retriever = TfidfRetriever(sample_petstore_chunks)
    results = retriever.retrieve(
        query="pets",
        top_k=5,
        method_filter=HTTPMethod.DELETE,
    )

    assert len(results) == 1
    assert results[0].chunk.method == HTTPMethod.DELETE
    assert results[0].chunk.path == "/pets/{petId}"


def test_retriever_empty_query(sample_petstore_chunks):
    retriever = TfidfRetriever(sample_petstore_chunks)
    results = retriever.retrieve(query="", top_k=3)
    assert len(results) == 3
    assert results[0].rank == 1


def test_retriever_empty_chunks():
    retriever = TfidfRetriever([])
    results = retriever.retrieve(query="anything")
    assert results == []


def test_get_by_endpoint(sample_petstore_chunks):
    retriever = TfidfRetriever(sample_petstore_chunks)
    chunk = retriever.get_by_endpoint("GET", "/pets")
    assert chunk is not None
    assert chunk.endpoint_key == "GET /pets"

    missing = retriever.get_by_endpoint("GET", "/nonexistent")
    assert missing is None
