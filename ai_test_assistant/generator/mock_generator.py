"""Deterministic mock test generator for offline mode, CI, and test harness validation."""

import json
from typing import List, Optional

from ai_test_assistant.parser.models import EndpointChunk, HTTPMethod


class MockClaudeGenerator:
    """Generates high-quality pytest suites offline without external network or LLM API calls."""

    def __init__(
        self,
        inject_hallucination: bool = False,
        inject_dangerous_import: bool = False,
        omit_negative_tests: bool = False,
        inject_syntax_error: bool = False,
    ):
        self.inject_hallucination = inject_hallucination
        self.inject_dangerous_import = inject_dangerous_import
        self.omit_negative_tests = omit_negative_tests
        self.inject_syntax_error = inject_syntax_error

    def generate(
        self,
        chunks: List[EndpointChunk],
        query: Optional[str] = None,
        base_url: str = "http://localhost:8000",
    ) -> str:
        """Generate pytest test code matching the provided chunks."""
        if self.inject_syntax_error:
            return "def test_invalid_syntax(:\n    assert True"

        imports = [
            "import pytest",
            "import requests",
            "import os",
        ]
        if self.inject_dangerous_import:
            imports.append("import subprocess")
            imports.append("import shutil")

        header = "\n".join(imports) + "\n\n"
        fixtures = f"""@pytest.fixture
def base_url():
    return os.getenv("BASE_URL", "{base_url.rstrip('/')}")


@pytest.fixture
def auth_headers():
    return {{"Authorization": "Bearer test-mock-token-xyz"}}

"""
        test_functions: List[str] = []

        for chunk in chunks:
            method = chunk.method.value.lower()
            safe_name = chunk.path.strip("/").replace("/", "_").replace("{", "").replace("}", "").replace("-", "_")
            if not safe_name:
                safe_name = "root"

            # Resolve URL format: replace {param} with mock value
            clean_path = chunk.path
            for p in chunk.parameters:
                clean_path = clean_path.replace(f"{{{p.name}}}", "123")

            # 1. Positive / Happy Path Test
            pos_code = f"""def test_{method}_{safe_name}_success(base_url, auth_headers):
    \"\"\"Verify successful response from {chunk.method.value} {chunk.path}\"\"\"
    url = f"{{base_url}}{clean_path}"
    headers = {{"Content-Type": "application/json"}}
"""
            if chunk.security:
                pos_code += "    headers.update(auth_headers)\n"

            if chunk.method in [HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH]:
                # Prepare mock payload
                payload = {"name": "sample_item", "status": "active"}
                if chunk.request_body and chunk.request_body.example:
                    payload = chunk.request_body.example
                payload_str = json.dumps(payload)
                pos_code += f"    payload = {payload_str}\n"
                pos_code += f"    response = requests.{method}(url, json=payload, headers=headers)\n"
            else:
                pos_code += f"    response = requests.{method}(url, headers=headers)\n"

            pos_code += "    assert response.status_code in [200, 201, 204]\n"
            pos_code += "    assert response.headers.get('Content-Type') is not None\n"
            if chunk.method != HTTPMethod.DELETE:
                pos_code += "    data = response.json()\n"
                pos_code += "    assert isinstance(data, (dict, list))\n"

            test_functions.append(pos_code)

            # 2. Negative Tests (if not disabled)
            if not self.omit_negative_tests:
                # Negative 404 test if path has parameter
                if "123" in clean_path:
                    path_404 = clean_path.replace("123", "999999")
                    neg_404 = f"""def test_{method}_{safe_name}_not_found(base_url, auth_headers):
    \"\"\"Negative test: Verify 404 for non-existent resource on {chunk.method.value} {chunk.path}\"\"\"
    url = f"{{base_url}}{path_404}"
    response = requests.{method}(url, headers=auth_headers)
    assert response.status_code == 404
"""
                    test_functions.append(neg_404)

                # Negative 400 Bad Request test for POST/PUT with empty payload
                if chunk.method in [HTTPMethod.POST, HTTPMethod.PUT]:
                    neg_400 = f"""def test_{method}_{safe_name}_invalid_payload(base_url, auth_headers):
    \"\"\"Negative test: Verify 400 Bad Request when required body is missing or malformed.\"\"\"
    url = f"{{base_url}}{clean_path}"
    response = requests.{method}(url, json={{}}, headers=auth_headers)
    assert response.status_code in [400, 422]
"""
                    test_functions.append(neg_400)

                # Negative 401 Unauthorized test if security is defined
                if chunk.security:
                    neg_401 = f"""def test_{method}_{safe_name}_unauthorized(base_url):
    \"\"\"Negative test: Verify 401 Unauthorized when request lacks authentication.\"\"\"
    url = f"{{base_url}}{clean_path}"
    response = requests.{method}(url, headers={{}})
    assert response.status_code in [401, 403]
"""
                    test_functions.append(neg_401)

        # Hallucination injection if requested
        if self.inject_hallucination:
            hallucinated_test = f"""def test_hallucinated_secret_admin_route(base_url):
    \"\"\"Deliberately invented endpoint not present in spec for evaluation harness testing.\"\"\"
    url = f"{{base_url}}/api/v1/internal/admin/wipe-database"
    response = requests.delete(url)
    assert response.status_code == 200
"""
            test_functions.append(hallucinated_test)

        if self.inject_dangerous_import:
            dangerous_func = """def test_exploit_sandbox():
    \"\"\"Dangerous command execution injected for safety scanner testing.\"\"\"
    subprocess.run(["echo", "exploit"], check=False)
    assert True
"""
            test_functions.append(dangerous_func)

        return header + fixtures + "\n\n".join(test_functions) + "\n"
