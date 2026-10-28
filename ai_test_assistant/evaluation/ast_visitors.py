"""AST Visitors for analyzing generated pytest test suites."""

import ast
import re
from typing import Any, Dict, List, Optional, Set, Tuple


class EndpointCall:
    """Represents an extracted HTTP request call from test code."""

    def __init__(self, method: str, raw_url: str, normalized_path: str, line_number: int):
        self.method = method.upper()
        self.raw_url = raw_url
        self.normalized_path = normalized_path
        self.line_number = line_number

    @property
    def key(self) -> str:
        return f"{self.method} {self.normalized_path}"

    def __repr__(self) -> str:
        return f"<EndpointCall {self.key} @ L{self.line_number}>"


class TestSuiteAstVisitor(ast.NodeVisitor):
    """Unified AST visitor extracting assertions, HTTP calls, test functions, and negative tests."""

    HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}
    HTTP_CLIENTS = {"requests", "httpx", "client", "session", "api_client"}

    def __init__(self):
        self.test_functions: List[str] = []
        self.assertions_count: int = 0
        self.pytest_raises_count: int = 0
        self.status_code_checks: int = 0
        self.body_json_checks: int = 0
        self.header_checks: int = 0
        self.endpoint_calls: List[EndpointCall] = []
        self.negative_test_functions: Set[str] = set()

        self._current_function: Optional[str] = None
        self._local_vars: Dict[str, str] = {}
        self._current_func_has_negative_indicator: bool = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track test functions and local variables inside each test."""
        prev_func = self._current_function
        prev_vars = self._local_vars.copy()
        prev_neg = self._current_func_has_negative_indicator

        if node.name.startswith("test_"):
            self.test_functions.append(node.name)
            self._current_function = node.name
            self._local_vars = {}
            self._current_func_has_negative_indicator = False

            # Check function name for negative test keywords
            name_lower = node.name.lower()
            if any(kw in name_lower for kw in [
                "negative", "invalid", "error", "fail", "not_found", "unauthorized",
                "forbidden", "bad_request", "400", "401", "403", "404", "422", "500"
            ]):
                self._current_func_has_negative_indicator = True

        self.generic_visit(node)

        if node.name.startswith("test_") and self._current_func_has_negative_indicator:
            self.negative_test_functions.add(node.name)

        self._current_function = prev_func
        self._local_vars = prev_vars
        self._current_func_has_negative_indicator = prev_neg

    def visit_Assign(self, node: ast.Assign) -> None:
        """Trace local variable assignments for URL building (e.g., url = f"{base_url}/users")."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id
                val = self._extract_string_value(node.value)
                if val is not None:
                    self._local_vars[var_name] = val
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        """Analyze assert statements and detect status codes / json checks."""
        self.assertions_count += 1
        self._analyze_comparison(node.test)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        """Analyze context managers like 'with pytest.raises(...):'."""
        for item in node.items:
            call = item.context_expr
            if isinstance(call, ast.Call):
                func = call.func
                # pytest.raises(...)
                if isinstance(func, ast.Attribute) and func.attr == "raises":
                    self.pytest_raises_count += 1
                    self.assertions_count += 1
                    if self._current_function:
                        self._current_func_has_negative_indicator = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Analyze HTTP calls (requests.get, client.post, etc.) and json() calls."""
        # Check for pytest.fail(...)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "fail":
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "pytest":
                self.assertions_count += 1

        # Check for response.json()
        if isinstance(node.func, ast.Attribute) and node.func.attr == "json":
            self.body_json_checks += 1

        # Check for HTTP calls like requests.get(...)
        method, is_http = self._get_http_method(node.func)
        if is_http and node.args:
            first_arg = node.args[0]
            raw_val = self._resolve_arg_value(first_arg)
            if raw_val:
                norm_path = self._normalize_endpoint_path(raw_val)
                self.endpoint_calls.append(
                    EndpointCall(
                        method=method,
                        raw_url=raw_val,
                        normalized_path=norm_path,
                        line_number=node.lineno,
                    )
                )

        self.generic_visit(node)

    def _get_http_method(self, func_node: ast.AST) -> Tuple[str, bool]:
        """Check if AST node represents an HTTP method call (e.g. requests.get or client.post)."""
        if isinstance(func_node, ast.Attribute):
            attr_name = func_node.attr.lower()
            if attr_name in self.HTTP_METHODS:
                # Direct caller like requests.get(...) or client.post(...)
                if isinstance(func_node.value, ast.Name):
                    caller = func_node.value.id.lower()
                    # Explicitly reject dictionary/object lookups like headers.get(...) or response.get(...)
                    if caller in {"headers", "header", "dict", "data", "json", "params", "cookies", "response", "res", "r"}:
                        return "", False
                    if caller in self.HTTP_CLIENTS or "client" in caller or "session" in caller or caller == "requests" or caller == "httpx":
                        return attr_name, True
                elif isinstance(func_node.value, ast.Attribute):
                    # Chained calls like self.client.get(...) or test_client.session.get(...)
                    chain_str = ast.unparse(func_node.value).lower() if hasattr(ast, "unparse") else ""
                    if any(bad in chain_str for bad in ["headers", "response.headers", ".headers"]):
                        return "", False
                    if any(c in chain_str for c in self.HTTP_CLIENTS):
                        return attr_name, True
        return "", False

    def _extract_string_value(self, node: ast.AST) -> Optional[str]:
        """Extract a string representation from literal or f-string."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        elif isinstance(node, ast.JoinedStr):
            # Reconstruct f-string pattern: replace expressions with placeholders
            parts: List[str] = []
            for part in node.values:
                if isinstance(part, ast.Constant):
                    parts.append(str(part.value))
                elif isinstance(part, ast.FormattedValue):
                    # Represent {expr} as parameter placeholder
                    parts.append("{param}")
            return "".join(parts)
        return None

    def _resolve_arg_value(self, node: ast.AST) -> Optional[str]:
        """Resolve argument node to a string URL, checking local variables if needed."""
        direct = self._extract_string_value(node)
        if direct is not None:
            return direct
        if isinstance(node, ast.Name) and node.id in self._local_vars:
            return self._local_vars[node.id]
        return None

    def _normalize_endpoint_path(self, raw: str) -> str:
        """Strip host/protocol and normalize path parameters to match OpenAPI specs."""
        # Strip scheme & host e.g. 'http://localhost:8000/api/v1/users' or '{base_url}/api/v1/users'
        clean = raw
        if "://" in clean:
            clean = clean.split("://", 1)[1]
            if "/" in clean:
                clean = "/" + clean.split("/", 1)[1]
            else:
                clean = "/"

        # Strip variable prefixes like '{base_url}' or '{BASE_URL}'
        clean = re.sub(r"^\{[^}]*\}", "", clean)

        # If no leading slash, add it
        if not clean.startswith("/"):
            clean = "/" + clean

        # Normalize path parameter values like /users/123 or /users/999999 or /users/{param} to standard {param}
        segments = clean.split("/")
        norm_segments: List[str] = []
        for seg in segments:
            if not seg:
                continue
            # If numeric or UUID or placeholder
            if seg.isdigit() or re.match(r"^[0-9a-fA-F-]{32,}$", seg) or seg == "{param}":
                norm_segments.append("{param}")
            else:
                norm_segments.append(seg)

        return "/" + "/".join(norm_segments)

    def _analyze_comparison(self, test_node: ast.AST) -> None:
        """Check if an assertion expression compares status codes or checks headers."""
        if isinstance(test_node, ast.Compare):
            left_str = ast.unparse(test_node.left) if hasattr(ast, "unparse") else ""
            if "status_code" in left_str:
                self.status_code_checks += 1
                # Check for 4xx or 5xx status codes
                for comp in test_node.comparators:
                    comp_str = ast.unparse(comp) if hasattr(ast, "unparse") else ""
                    if any(err_code in comp_str for err_code in ["400", "401", "403", "404", "422", "500"]):
                        self._current_func_has_negative_indicator = True
            elif "header" in left_str:
                self.header_checks += 1
