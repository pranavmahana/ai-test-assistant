"""Unit tests for the evaluation harness and AST scoring."""

import pytest

from ai_test_assistant.evaluation.evaluator import TestEvaluator
from ai_test_assistant.generator.mock_generator import MockClaudeGenerator


def test_evaluator_valid_suite(sample_petstore_chunks):
    generator = MockClaudeGenerator()
    code = generator.generate(sample_petstore_chunks)

    evaluator = TestEvaluator()
    report = evaluator.evaluate(code, sample_petstore_chunks)

    assert report.syntax.is_valid is True
    assert report.syntax.score == 20.0
    assert report.assertions.total_assertions > 0
    assert report.assertions.assertions_per_test >= 1.5
    assert report.hallucinations.hallucination_count == 0
    assert report.hallucinations.score == 25.0
    assert report.coverage.coverage_percentage == 100.0
    assert report.negative_tests.negative_tests > 0
    assert report.composite_score >= 85.0
    assert report.passed is True
    assert report.grade in ("A", "A+")


def test_evaluator_syntax_error(sample_petstore_chunks):
    bad_code = "def test_broken(:\n    assert True"
    evaluator = TestEvaluator()
    report = evaluator.evaluate(bad_code, sample_petstore_chunks)

    assert report.syntax.is_valid is False
    assert report.composite_score == 0.0
    assert report.grade == "F"
    assert report.passed is False


def test_evaluator_detects_hallucinated_endpoint(sample_petstore_chunks):
    generator = MockClaudeGenerator(inject_hallucination=True)
    code = generator.generate(sample_petstore_chunks)

    evaluator = TestEvaluator()
    report = evaluator.evaluate(code, sample_petstore_chunks)

    assert report.hallucinations.hallucination_count >= 1
    assert any("wipe-database" in h for h in report.hallucinations.hallucinated_endpoints)
    # Hallucination causes score penalty and failure
    assert report.hallucinations.score < 25.0
    assert report.passed is False


def test_evaluator_penalizes_omitted_negative_tests(sample_petstore_chunks):
    generator = MockClaudeGenerator(omit_negative_tests=True)
    code = generator.generate(sample_petstore_chunks)

    evaluator = TestEvaluator()
    report = evaluator.evaluate(code, sample_petstore_chunks)

    assert report.negative_tests.negative_tests == 0
    assert report.negative_tests.score == 0.0
    assert any("negative" in rec.lower() for rec in report.recommendations)


def test_evaluator_json_export(sample_petstore_chunks):
    generator = MockClaudeGenerator()
    code = generator.generate(sample_petstore_chunks)

    evaluator = TestEvaluator()
    report = evaluator.evaluate(code, sample_petstore_chunks)
    data = report.to_dict()

    assert "composite_score" in data
    assert "grade" in data
    assert "metrics" in data
    assert "syntax" in data["metrics"]
