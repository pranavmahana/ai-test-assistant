"""Unit tests for prompt-injection red-team benchmark."""

from ai_test_assistant.redteam.redteam_harness import RedTeamHarness


def test_redteam_benchmark_run():
    harness = RedTeamHarness()
    report = harness.run_benchmark()

    assert report.total_attacks == 4
    assert report.passed_attacks == 4
    assert report.resistance_percentage == 100.0
    assert report.passed is True

    for attack in report.results:
        assert attack.passed is True
        assert attack.safety_scan_passed is True
        assert attack.anti_hallucination_passed is True
