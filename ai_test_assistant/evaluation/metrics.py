"""Metrics models and rubric calculations for test suite evaluation."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai_test_assistant.config import DEFAULT_WEIGHTS, EvaluationWeights


@dataclass
class SyntaxMetric:
    """Evaluates Python syntax validity via AST compilation."""
    is_valid: bool
    error_message: Optional[str] = None
    error_line: Optional[int] = None
    score: float = 0.0  # Max: weights.syntax_validity (20)


@dataclass
class AssertionMetric:
    """Evaluates the density and diversity of test assertions."""
    total_assertions: int
    test_count: int
    assertions_per_test: float
    status_code_checks: int
    body_json_checks: int
    header_checks: int
    score: float = 0.0  # Max: weights.assertion_quality (20)


@dataclass
class HallucinationMetric:
    """Evaluates whether any tested endpoints were hallucinated / not in OpenAPI spec."""
    tested_endpoints: List[str]
    valid_spec_endpoints: List[str]
    hallucinated_endpoints: List[str]
    hallucination_count: int
    score: float = 0.0  # Max: weights.hallucination_penalty (25)


@dataclass
class CoverageMetric:
    """Evaluates the percentage of spec endpoints covered by tests."""
    target_count: int
    covered_count: int
    covered_endpoints: List[str]
    uncovered_endpoints: List[str]
    coverage_percentage: float
    score: float = 0.0  # Max: weights.endpoint_coverage (20)


@dataclass
class NegativeTestMetric:
    """Evaluates presence and ratio of negative / edge-case tests."""
    total_tests: int
    negative_tests: int
    negative_test_ratio: float
    negative_test_names: List[str]
    score: float = 0.0  # Max: weights.negative_test_presence (15)


@dataclass
class EvaluationReport:
    """Comprehensive evaluation score card for a generated test suite."""
    syntax: SyntaxMetric
    assertions: AssertionMetric
    hallucinations: HallucinationMetric
    coverage: CoverageMetric
    negative_tests: NegativeTestMetric
    composite_score: float
    grade: str
    passed: bool
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to JSON-serializable dictionary."""
        return {
            "composite_score": round(self.composite_score, 2),
            "grade": self.grade,
            "passed": self.passed,
            "metrics": {
                "syntax": {
                    "is_valid": self.syntax.is_valid,
                    "error": self.syntax.error_message,
                    "score": round(self.syntax.score, 2),
                },
                "assertions": {
                    "total": self.assertions.total_assertions,
                    "per_test": round(self.assertions.assertions_per_test, 2),
                    "status_code_checks": self.assertions.status_code_checks,
                    "json_checks": self.assertions.body_json_checks,
                    "header_checks": self.assertions.header_checks,
                    "score": round(self.assertions.score, 2),
                },
                "hallucinations": {
                    "count": self.hallucinations.hallucination_count,
                    "hallucinated_endpoints": self.hallucinations.hallucinated_endpoints,
                    "score": round(self.hallucinations.score, 2),
                },
                "coverage": {
                    "target_count": self.coverage.target_count,
                    "covered_count": self.coverage.covered_count,
                    "percentage": round(self.coverage.coverage_percentage, 2),
                    "score": round(self.coverage.score, 2),
                },
                "negative_tests": {
                    "total_tests": self.negative_tests.total_tests,
                    "negative_tests": self.negative_tests.negative_tests,
                    "ratio": round(self.negative_tests.negative_test_ratio, 2),
                    "score": round(self.negative_tests.score, 2),
                },
            },
            "recommendations": self.recommendations,
        }
