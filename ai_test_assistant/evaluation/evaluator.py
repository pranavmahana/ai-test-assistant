"""Evaluation engine that scores generated test suites across five core dimensions."""

import ast
import re
from typing import Any, Dict, List, Optional, Set

from ai_test_assistant.config import DEFAULT_WEIGHTS, EvaluationWeights
from ai_test_assistant.evaluation.ast_visitors import EndpointCall, TestSuiteAstVisitor
from ai_test_assistant.evaluation.metrics import (
    AssertionMetric,
    CoverageMetric,
    EvaluationReport,
    HallucinationMetric,
    NegativeTestMetric,
    SyntaxMetric,
)
from ai_test_assistant.parser.models import EndpointChunk


class TestEvaluator:
    """Evaluates generated pytest code against OpenAPI endpoint specifications."""
    __test__ = False

    def __init__(self, weights: Optional[EvaluationWeights] = None):
        self.weights = weights or DEFAULT_WEIGHTS
        self.weights.validate()

    def evaluate(self, code: str, target_chunks: List[EndpointChunk]) -> EvaluationReport:
        """Run complete evaluation harness on the provided test code."""
        recommendations: List[str] = []

        # 1. Syntax Validity Check
        syntax_metric = self._check_syntax(code)
        if not syntax_metric.is_valid:
            recommendations.append(f"Fix syntax error: {syntax_metric.error_message}")
            return EvaluationReport(
                syntax=syntax_metric,
                assertions=AssertionMetric(0, 0, 0.0, 0, 0, 0, 0.0),
                hallucinations=HallucinationMetric([], [], [], 0, 0.0),
                coverage=CoverageMetric(len(target_chunks), 0, [], [c.endpoint_key for c in target_chunks], 0.0, 0.0),
                negative_tests=NegativeTestMetric(0, 0, 0.0, [], 0.0),
                composite_score=0.0,
                grade="F",
                passed=False,
                recommendations=recommendations,
            )

        # 2. AST Visitor Extraction
        tree = ast.parse(code)
        visitor = TestSuiteAstVisitor()
        visitor.visit(tree)

        test_count = len(visitor.test_functions)
        if test_count == 0:
            recommendations.append("No functions starting with 'test_' were detected.")

        # 3. Assertion Quality Scoring
        assertion_metric = self._score_assertions(visitor, test_count)
        if assertion_metric.assertions_per_test < 1.5:
            recommendations.append("Increase assertion density: aim for at least 2 assertions per test.")

        # 4. Hallucinated Endpoints Scoring
        hallucination_metric = self._score_hallucinations(visitor.endpoint_calls, target_chunks)
        if hallucination_metric.hallucination_count > 0:
            recommendations.append(
                f"Eliminate hallucinated endpoints not in spec: {hallucination_metric.hallucinated_endpoints}"
            )

        # 5. Endpoint Coverage Scoring
        coverage_metric = self._score_coverage(visitor.endpoint_calls, target_chunks)
        if coverage_metric.coverage_percentage < 100.0:
            recommendations.append(
                f"Improve coverage: {len(coverage_metric.uncovered_endpoints)} endpoint(s) lack tests: {coverage_metric.uncovered_endpoints}"
            )

        # 6. Negative Test Presence Scoring
        negative_metric = self._score_negative_tests(visitor, test_count)
        if negative_metric.negative_tests == 0:
            recommendations.append("Add negative tests for invalid payloads, missing auth, and 404 errors.")

        # 7. Composite Score & Grade
        composite = (
            syntax_metric.score
            + assertion_metric.score
            + hallucination_metric.score
            + coverage_metric.score
            + negative_metric.score
        )

        grade = self._calculate_grade(composite)
        passed = composite >= 70.0 and syntax_metric.is_valid and hallucination_metric.hallucination_count == 0

        return EvaluationReport(
            syntax=syntax_metric,
            assertions=assertion_metric,
            hallucinations=hallucination_metric,
            coverage=coverage_metric,
            negative_tests=negative_metric,
            composite_score=composite,
            grade=grade,
            passed=passed,
            recommendations=recommendations,
        )

    def _check_syntax(self, code: str) -> SyntaxMetric:
        """Verify code compiles as valid Python syntax."""
        try:
            ast.parse(code)
            return SyntaxMetric(is_valid=True, score=self.weights.syntax_validity)
        except SyntaxError as e:
            return SyntaxMetric(
                is_valid=False,
                error_message=str(e),
                error_line=e.lineno,
                score=0.0,
            )

    def _score_assertions(self, visitor: TestSuiteAstVisitor, test_count: int) -> AssertionMetric:
        """Score test assertions based on density and diversity."""
        total = visitor.assertions_count
        per_test = (total / test_count) if test_count > 0 else 0.0

        # Score calculation: up to weights.assertion_quality (20 pts)
        # 2+ assertions/test + diverse checks = 20 pts
        score = 0.0
        if per_test >= 2.0:
            score += 12.0
        elif per_test >= 1.0:
            score += 8.0
        elif per_test > 0:
            score += 4.0

        # Status code verification bonus (up to 4 pts)
        if visitor.status_code_checks >= test_count and test_count > 0:
            score += 4.0
        elif visitor.status_code_checks > 0:
            score += 2.0

        # Payload / JSON body verification bonus (up to 4 pts)
        if visitor.body_json_checks > 0:
            score += 4.0

        score = min(score, self.weights.assertion_quality)

        return AssertionMetric(
            total_assertions=total,
            test_count=test_count,
            assertions_per_test=per_test,
            status_code_checks=visitor.status_code_checks,
            body_json_checks=visitor.body_json_checks,
            header_checks=visitor.header_checks,
            score=score,
        )

    def _score_hallucinations(
        self,
        calls: List[EndpointCall],
        target_chunks: List[EndpointChunk],
    ) -> HallucinationMetric:
        """Detect and penalize any endpoint called in tests that is not present in target chunks."""
        valid_endpoints = [c.endpoint_key for c in target_chunks]
        tested_endpoints = list({call.key for call in calls})
        hallucinated: List[str] = []

        for call in calls:
            matched = False
            for chunk in target_chunks:
                if self._match_endpoint(call, chunk):
                    matched = True
                    break
            if not matched:
                if call.key not in hallucinated:
                    hallucinated.append(call.key)

        h_count = len(hallucinated)

        # 25 pts for 0 hallucinations, 10 pts for 1, 0 pts for 2+
        if h_count == 0:
            score = self.weights.hallucination_penalty
        elif h_count == 1:
            score = self.weights.hallucination_penalty * 0.4
        else:
            score = 0.0

        return HallucinationMetric(
            tested_endpoints=tested_endpoints,
            valid_spec_endpoints=valid_endpoints,
            hallucinated_endpoints=hallucinated,
            hallucination_count=h_count,
            score=score,
        )

    def _score_coverage(
        self,
        calls: List[EndpointCall],
        target_chunks: List[EndpointChunk],
    ) -> CoverageMetric:
        """Compute the ratio of target spec endpoints covered by tests."""
        target_count = len(target_chunks)
        if target_count == 0:
            return CoverageMetric(0, 0, [], [], 100.0, self.weights.endpoint_coverage)

        covered: List[str] = []
        uncovered: List[str] = []

        for chunk in target_chunks:
            chunk_matched = any(self._match_endpoint(call, chunk) for call in calls)
            if chunk_matched:
                covered.append(chunk.endpoint_key)
            else:
                uncovered.append(chunk.endpoint_key)

        covered_count = len(covered)
        percentage = (covered_count / target_count) * 100.0
        score = (percentage / 100.0) * self.weights.endpoint_coverage

        return CoverageMetric(
            target_count=target_count,
            covered_count=covered_count,
            covered_endpoints=covered,
            uncovered_endpoints=uncovered,
            coverage_percentage=percentage,
            score=score,
        )

    def _score_negative_tests(
        self, visitor: TestSuiteAstVisitor, test_count: int
    ) -> NegativeTestMetric:
        """Score the presence and proportion of negative / edge-case tests."""
        neg_count = len(visitor.negative_test_functions)
        ratio = (neg_count / test_count) if test_count > 0 else 0.0

        # Full score (15 pts) if at least 20% of tests are negative scenarios
        if ratio >= 0.20:
            score = self.weights.negative_test_presence
        elif ratio > 0:
            score = self.weights.negative_test_presence * (ratio / 0.20)
        else:
            score = 0.0

        return NegativeTestMetric(
            total_tests=test_count,
            negative_tests=neg_count,
            negative_test_ratio=ratio,
            negative_test_names=sorted(list(visitor.negative_test_functions)),
            score=score,
        )

    def _match_endpoint(self, call: EndpointCall, chunk: EndpointChunk) -> bool:
        """Check if an extracted HTTP call matches an OpenAPI endpoint specification."""
        if call.method != chunk.method.value.upper():
            return False

        # Convert chunk path with parameters e.g. /pets/{petId} into a regex pattern
        spec_path = chunk.path
        # Pattern replaces {param} with regex segment [^/]+
        pattern = "^" + re.sub(r"\{[^}]+\}", r"[^/]+", spec_path) + "$"

        call_path = call.normalized_path

        # Direct match or regex pattern match
        if call_path == spec_path:
            return True
        if re.match(pattern, call_path):
            return True

        # Handle call_path using placeholder {param} vs chunk path
        call_sub = re.sub(r"\{param\}", r"[^/]+", call_path)
        if re.match("^" + call_sub + "$", spec_path):
            return True

        return False

    @staticmethod
    def _calculate_grade(score: float) -> str:
        """Convert a numerical composite score to a letter grade."""
        if score >= 90.0:
            return "A+"
        elif score >= 80.0:
            return "A"
        elif score >= 70.0:
            return "B"
        elif score >= 60.0:
            return "C"
        return "F"
