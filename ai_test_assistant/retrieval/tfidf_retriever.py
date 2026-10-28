"""TF-IDF Lexical Retrieval Engine for OpenAPI Endpoint Chunks."""

import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Set

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ai_test_assistant.parser.models import EndpointChunk, HTTPMethod


@dataclass
class RetrievalResult:
    """Represents a retrieved endpoint chunk with its relevance score and rank."""
    chunk: EndpointChunk
    score: float
    rank: int

    @property
    def endpoint_key(self) -> str:
        return self.chunk.endpoint_key


def custom_endpoint_tokenizer(text: str) -> List[str]:
    """Tokenize text into sub-tokens, splitting path separators, camelCase, and snake_case."""
    # Split camelCase (e.g., userId -> user id)
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    # Split non-alphanumeric characters (slashes, hyphens, underscores, braces)
    s2 = re.sub(r"[^a-zA-Z0-9\s]", " ", s1)
    # Normalize to lowercase and split on whitespace
    raw_tokens = s2.lower().split()

    tokens: List[str] = []
    for token in raw_tokens:
        if len(token) > 1:
            tokens.append(token)
    return tokens


class TfidfRetriever:
    """Indexes and retrieves endpoint chunks using TF-IDF vectorization and cosine similarity."""

    def __init__(
        self,
        chunks: List[EndpointChunk],
        ngram_range: tuple = (1, 2),
        sublinear_tf: bool = True,
    ):
        self.chunks = list(chunks)
        self.ngram_range = ngram_range
        self.sublinear_tf = sublinear_tf
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self._is_indexed = False

        if self.chunks:
            self._build_index()

    def _build_index(self) -> None:
        """Construct the TF-IDF matrix from endpoint documents."""
        documents = [chunk.to_search_document() for chunk in self.chunks]

        self.vectorizer = TfidfVectorizer(
            tokenizer=custom_endpoint_tokenizer,
            ngram_range=self.ngram_range,
            sublinear_tf=self.sublinear_tf,
            lowercase=True,
            token_pattern=None,  # Suppress warning when custom tokenizer is supplied
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(documents)
        self._is_indexed = True

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        method_filter: Optional[HTTPMethod] = None,
        tag_filter: Optional[str] = None,
        path_prefix: Optional[str] = None,
    ) -> List[RetrievalResult]:
        """Search the indexed endpoint chunks given a natural language or keyword query."""
        if not self._is_indexed or not self.chunks or self.vectorizer is None or self.tfidf_matrix is None:
            return []

        clean_query = query.strip()
        if not clean_query:
            # If query is empty, return top_k chunks with score 0.0
            selected = self.chunks[:top_k]
            return [RetrievalResult(chunk=c, score=0.0, rank=i + 1) for i, c in enumerate(selected)]

        query_vec = self.vectorizer.transform([clean_query])
        scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        # Sort indices by descending score
        ranked_indices = np.argsort(scores)[::-1]

        results: List[RetrievalResult] = []
        rank_counter = 1

        for idx in ranked_indices:
            score = float(scores[idx])
            chunk = self.chunks[idx]

            # Apply min_score threshold if any matches occurred
            if score < min_score:
                continue

            # Optional filters
            if method_filter and chunk.method != method_filter:
                continue

            if tag_filter and (not chunk.tags or tag_filter.lower() not in [t.lower() for t in chunk.tags]):
                continue

            if path_prefix and not chunk.path.startswith(path_prefix):
                continue

            results.append(RetrievalResult(chunk=chunk, score=round(score, 4), rank=rank_counter))
            rank_counter += 1

            if len(results) >= top_k:
                break

        return results

    def get_by_endpoint(self, method: str, path: str) -> Optional[EndpointChunk]:
        """Look up an endpoint directly by method and path."""
        norm_key = f"{method.upper()} {path.strip()}"
        for chunk in self.chunks:
            if chunk.endpoint_key == norm_key:
                return chunk
        return None
