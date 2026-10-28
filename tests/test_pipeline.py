"""End-to-end integration tests for the Pipeline class."""

from ai_test_assistant.pipeline import Pipeline


def test_pipeline_e2e_run(petstore_spec_path):
    pipeline = Pipeline(spec_source=petstore_spec_path, use_mock=True)
    result = pipeline.run(query="list and create pets", top_k=2)

    assert result.passed is True
    assert result.safety_report.is_safe is True
    assert result.evaluation_report.passed is True
    assert result.evaluation_report.composite_score >= 80.0
    assert len(result.target_chunks) == 2
    assert result.retrieval_results is not None
    assert len(result.retrieval_results) == 2
    assert "def test_" in result.generated_code
