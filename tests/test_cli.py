"""Integration tests for CLI subcommands."""

from pathlib import Path
import pytest
import sys

from ai_test_assistant.cli import main


def test_cli_help(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ai-test-assistant", "--help"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "AI Test Assistant" in captured.out


def test_cli_chunk(petstore_spec_path, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ai-test-assistant", "chunk", "--spec", str(petstore_spec_path)])
    main()
    captured = capsys.readouterr()
    assert "Endpoint Chunks" in captured.out
    assert "GET" in captured.out
    assert "/pets" in captured.out


def test_cli_retrieve(petstore_spec_path, capsys, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["ai-test-assistant", "retrieve", "--spec", str(petstore_spec_path), "--query", "create pet"],
    )
    main()
    captured = capsys.readouterr()
    assert "TF-IDF Retrieval Results" in captured.out
    assert "POST /pets" in captured.out


def test_cli_generate_mock(petstore_spec_path, tmp_path, capsys, monkeypatch):
    out_file = tmp_path / "test_out.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ai-test-assistant",
            "generate",
            "--spec",
            str(petstore_spec_path),
            "--mock",
            "-o",
            str(out_file),
        ],
    )
    main()
    captured = capsys.readouterr()
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "def test_get_pets_success" in content


def test_cli_evaluate(petstore_spec_path, tmp_path, capsys, monkeypatch):
    # First generate tests
    test_file = tmp_path / "generated_tests.py"
    monkeypatch.setattr(
        sys,
        "argv",
        ["ai-test-assistant", "generate", "--spec", str(petstore_spec_path), "--mock", "-o", str(test_file)],
    )
    main()

    # Then evaluate
    monkeypatch.setattr(
        sys,
        "argv",
        ["ai-test-assistant", "evaluate", "--spec", str(petstore_spec_path), "--test-file", str(test_file)],
    )
    main()
    captured = capsys.readouterr()
    assert "Evaluation Scorecard" in captured.out
    assert "VERDICT: PASSED" in captured.out


def test_cli_scan(tmp_path, capsys, monkeypatch):
    safe_file = tmp_path / "safe.py"
    safe_file.write_text("import pytest\ndef test_ok(): assert True", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["ai-test-assistant", "scan", "--target", str(safe_file)])
    main()
    captured = capsys.readouterr()
    assert "PASSED" in captured.out

    unsafe_file = tmp_path / "unsafe.py"
    unsafe_file.write_text("import subprocess\ndef test_bad(): subprocess.run(['ls'])", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["ai-test-assistant", "scan", "--target", str(unsafe_file)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    captured_err = capsys.readouterr()
    assert "FAILED" in captured_err.out


def test_cli_redteam(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ai-test-assistant", "redteam"])
    main()
    captured = capsys.readouterr()
    assert "Prompt-Injection Red-Team Benchmark" in captured.out
    assert "ALL ADVERSARIAL ATTACKS SUCCESSFULLY DEFENDED" in captured.out
