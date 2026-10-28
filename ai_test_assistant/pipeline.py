"""End-to-end Pipeline connecting Parsing, Retrieval, Generation, Safety, and Evaluation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Union

from ai_test_assistant.evaluation.evaluator import TestEvaluator
from ai_test_assistant.evaluation.metrics import EvaluationReport
from ai_test_assistant.generator.claude_client import ClaudeTestGenerator
from ai_test_assistant.generator.mock_generator import MockClaudeGenerator
from ai_test_assistant.parser.chunker import EndpointChunker
from ai_test_assistant.parser.models import EndpointChunk
from ai_test_assistant.parser.spec_parser import SpecParser
from ai_test_assistant.retrieval.tfidf_retriever import RetrievalResult, TfidfRetriever
from ai_test_assistant.security.safety_scanner import SafetyReport, SafetyScanner


@dataclass
class PipelineResult:
    """Full outcome of an end-to-end test generation and evaluation run."""
    generated_code: str
    target_chunks: List[EndpointChunk]
    retrieval_results: Optional[List[RetrievalResult]]
    evaluation_report: EvaluationReport
    safety_report: SafetyReport

    @property
    def passed(self) -> bool:
        return self.evaluation_report.passed and self.safety_report.is_safe


class Pipeline:
    """Orchestrates parsing, retrieval, LLM test generation, AST safety scanning, and evaluation."""

    def __init__(
        self,
        spec_source: Union[str, Path],
        use_mock: bool = False,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        # 1. Parse specification
        if isinstance(spec_source, Path) or (isinstance(spec_source, str) and (spec_source.endswith(".json") or spec_source.endswith(".yaml") or spec_source.endswith(".yml")) and Path(spec_source).exists()):
            self.parser = SpecParser.from_file(spec_source)
        else:
            self.parser = SpecParser.from_string(str(spec_source))

        # 2. Chunk endpoints
        self.chunker = EndpointChunker(self.parser)
        self.chunks = self.chunker.chunk_all()

        # 3. Index in TF-IDF Retriever
        self.retriever = TfidfRetriever(self.chunks)

        # 4. Initialize Generator (Claude with auto-fallback to Mock if offline or requested)
        self.use_mock = use_mock
        if use_mock:
            self.generator = MockClaudeGenerator()
        else:
            try:
                self.generator = ClaudeTestGenerator(api_key=api_key, **({"model": model} if model else {}))
            except Exception:
                # Fallback to mock generator if Claude client cannot be initialized
                self.generator = MockClaudeGenerator()
                self.use_mock = True

        # 5. Evaluator & Safety Scanner
        self.evaluator = TestEvaluator()
        self.safety_scanner = SafetyScanner()

    def run(
        self,
        query: Optional[str] = None,
        top_k: int = 5,
        base_url: Optional[str] = None,
    ) -> PipelineResult:
        """Run the end-to-end pipeline: retrieve -> generate -> scan -> evaluate."""
        target_base_url = base_url or self.parser.base_url

        # Step 1: Retrieval
        retrieval_results = None
        if query:
            retrieval_results = self.retriever.retrieve(query=query, top_k=top_k)
            target_chunks = [r.chunk for r in retrieval_results]
        else:
            target_chunks = self.chunks[:top_k] if len(self.chunks) > top_k else self.chunks

        if not target_chunks:
            target_chunks = self.chunks

        # Step 2: Generation
        generated_code = self.generator.generate(
            chunks=target_chunks,
            query=query,
            base_url=target_base_url,
        )

        # Step 3: AST Safety Scanning
        safety_report = self.safety_scanner.scan(generated_code)

        # Step 4: Evaluation Harness
        evaluation_report = self.evaluator.evaluate(
            code=generated_code,
            target_chunks=target_chunks,
        )

        return PipelineResult(
            generated_code=generated_code,
            target_chunks=target_chunks,
            retrieval_results=retrieval_results,
            evaluation_report=evaluation_report,
            safety_report=safety_report,
        )
