"""Unit tests for test generators (Mock and Claude client extraction)."""

import pytest

from ai_test_assistant.generator.claude_client import ClaudeTestGenerator
from ai_test_assistant.generator.mock_generator import MockClaudeGenerator


def test_mock_generator_produces_valid_pytest(sample_petstore_chunks):
    generator = MockClaudeGenerator()
    code = generator.generate(sample_petstore_chunks)

    assert "import pytest" in code
    assert "import requests" in code
    assert "def test_" in code
    assert "def base_url" in code
    assert "assert response.status_code" in code


def test_mock_generator_includes_negative_tests(sample_petstore_chunks):
    generator = MockClaudeGenerator(omit_negative_tests=False)
    code = generator.generate(sample_petstore_chunks)

    assert "not_found" in code
    assert "invalid_payload" in code
    assert "404" in code
    assert "400" in code


def test_mock_generator_inject_hallucination(sample_petstore_chunks):
    generator = MockClaudeGenerator(inject_hallucination=True)
    code = generator.generate(sample_petstore_chunks)

    assert "/api/v1/internal/admin/wipe-database" in code


def test_mock_generator_inject_dangerous_import(sample_petstore_chunks):
    generator = MockClaudeGenerator(inject_dangerous_import=True)
    code = generator.generate(sample_petstore_chunks)

    assert "import subprocess" in code


def test_claude_extract_code_from_markdown():
    markdown_resp = """Here is your test suite:
```python
import pytest
import requests

def test_health():
    assert True
```
Hope this helps!"""
    code = ClaudeTestGenerator.extract_code(markdown_resp)
    assert code.startswith("import pytest")
    assert "def test_health" in code
    assert "```" not in code


def test_claude_client_missing_key():
    client = ClaudeTestGenerator(api_key=None)
    with pytest.raises(ValueError):
        _ = client.client
