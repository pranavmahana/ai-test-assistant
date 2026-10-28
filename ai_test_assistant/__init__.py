"""AI Test Assistant - LLM-Powered API Test Generation & Evaluation Pipeline."""

__version__ = "0.1.0"
__author__ = "Pranav Mahana"

from ai_test_assistant.config import DEFAULT_WEIGHTS, EvaluationWeights
from ai_test_assistant.evaluation.ast_visitors import EndpointCall, TestSuiteAstVisitor
from ai_test_assistant.evaluation.evaluator import TestEvaluator
from ai_test_assistant.evaluation.metrics import (
    AssertionMetric,
    CoverageMetric,
    EvaluationReport,
    HallucinationMetric,
    NegativeTestMetric,
    SyntaxMetric,
)
from ai_test_assistant.generator.claude_client import ClaudeTestGenerator
from ai_test_assistant.generator.mock_generator import MockClaudeGenerator
from ai_test_assistant.generator.prompt_builder import PromptBuilder
from ai_test_assistant.parser.chunker import EndpointChunker
from ai_test_assistant.parser.models import (
    EndpointChunk,
    HTTPMethod,
    ParameterLocation,
    ParameterSpec,
    RequestBodySpec,
    ResponseSpec,
)
from ai_test_assistant.parser.spec_parser import SpecParser
from ai_test_assistant.pipeline import Pipeline, PipelineResult
from ai_test_assistant.redteam.redteam_harness import (
    RedTeamAttackResult,
    RedTeamHarness,
    RedTeamReport,
)
from ai_test_assistant.retrieval.tfidf_retriever import (
    RetrievalResult,
    TfidfRetriever,
    custom_endpoint_tokenizer,
)
from ai_test_assistant.security.safety_scanner import (
    SafetyReport,
    SafetyScanner,
    SafetyViolation,
    Severity,
)
from ai_test_assistant.security.sanitizer import SpecSanitizer

__all__ = [
    # Top-level pipeline
    "Pipeline",
    "PipelineResult",
    # Specification parsing & chunking
    "SpecParser",
    "EndpointChunker",
    "EndpointChunk",
    "HTTPMethod",
    "ParameterLocation",
    "ParameterSpec",
    "RequestBodySpec",
    "ResponseSpec",
    # Retrieval
    "TfidfRetriever",
    "RetrievalResult",
    "custom_endpoint_tokenizer",
    # Test Generation
    "PromptBuilder",
    "ClaudeTestGenerator",
    "MockClaudeGenerator",
    # Evaluation
    "TestEvaluator",
    "EvaluationReport",
    "EvaluationWeights",
    "DEFAULT_WEIGHTS",
    "SyntaxMetric",
    "AssertionMetric",
    "HallucinationMetric",
    "CoverageMetric",
    "NegativeTestMetric",
    "TestSuiteAstVisitor",
    "EndpointCall",
    # Security & Sanitization
    "SafetyScanner",
    "SafetyReport",
    "SafetyViolation",
    "Severity",
    "SpecSanitizer",
    # Red-Teaming
    "RedTeamHarness",
    "RedTeamReport",
    "RedTeamAttackResult",
]
