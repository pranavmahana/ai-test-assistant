"""AST-based safety scanner detecting dangerous imports, RCE payloads, and malicious network calls."""

import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set

from ai_test_assistant.config import (
    BLOCKED_HOST_PATTERNS,
    DANGEROUS_FUNCTIONS,
    DANGEROUS_MODULES,
)


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class SafetyViolation:
    """Represents a single security violation detected in the code."""
    rule: str
    message: str
    line_number: Optional[int] = None
    severity: Severity = Severity.HIGH


@dataclass
class SafetyReport:
    """Aggregated safety report resulting from an AST security scan."""
    is_safe: bool
    violations: List[SafetyViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(v.severity == Severity.CRITICAL for v in self.violations)


class SafetyVisitor(ast.NodeVisitor):
    """Traverses Python AST to identify dangerous constructs, imports, and calls."""

    def __init__(self, allowed_os_attributes: Optional[Set[str]] = None):
        self.violations: List[SafetyViolation] = []
        self.warnings: List[str] = []
        # Allow benign environment variable reads from os (e.g., os.getenv, os.environ.get)
        self.allowed_os_attributes = allowed_os_attributes or {"getenv", "environ"}

    def visit_Import(self, node: ast.Import) -> None:
        """Inspect 'import module' statements."""
        for alias in node.names:
            mod_name = alias.name.split(".")[0]
            if mod_name in DANGEROUS_MODULES and mod_name != "os":
                self.violations.append(
                    SafetyViolation(
                        rule="DISALLOWED_MODULE_IMPORT",
                        message=f"Disallowed module import: '{alias.name}'.",
                        line_number=node.lineno,
                        severity=Severity.CRITICAL,
                    )
                )
            elif mod_name == "os":
                self.warnings.append(
                    f"Line {node.lineno}: 'os' module imported. Ensure only read-only env access is used."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Inspect 'from module import name' statements."""
        if node.module:
            root_mod = node.module.split(".")[0]
            if root_mod in DANGEROUS_MODULES and root_mod != "os":
                self.violations.append(
                    SafetyViolation(
                        rule="DISALLOWED_FROM_IMPORT",
                        message=f"Disallowed module import: 'from {node.module} import ...'",
                        line_number=node.lineno,
                        severity=Severity.CRITICAL,
                    )
                )
            elif root_mod == "os":
                for alias in node.names:
                    if alias.name not in self.allowed_os_attributes:
                        self.violations.append(
                            SafetyViolation(
                                rule="UNSAFE_OS_FUNCTION_IMPORT",
                                message=f"Disallowed os import: 'from os import {alias.name}'.",
                                line_number=node.lineno,
                                severity=Severity.HIGH,
                            )
                        )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Inspect function calls for dangerous builtins, os methods, or malicious network targets."""
        # Check direct calls like eval(...) or exec(...)
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in DANGEROUS_FUNCTIONS:
                self.violations.append(
                    SafetyViolation(
                        rule="DANGEROUS_BUILTIN_CALL",
                        message=f"Call to prohibited builtin function '{func_name}()'.",
                        line_number=node.lineno,
                        severity=Severity.CRITICAL,
                    )
                )
            elif func_name == "open":
                # Check if opened for writing
                for arg in node.args[1:]:
                    if isinstance(arg, ast.Constant) and any(m in str(arg.value) for m in ["w", "a", "+"]):
                        self.violations.append(
                            SafetyViolation(
                                rule="UNSAFE_FILE_WRITE",
                                message="File opened in write/append mode.",
                                line_number=node.lineno,
                                severity=Severity.HIGH,
                            )
                        )

        # Check attribute calls like os.system(...) or subprocess.Popen(...)
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if isinstance(node.func.value, ast.Name):
                caller_name = node.func.value.id
                if caller_name == "os" and attr_name not in self.allowed_os_attributes:
                    self.violations.append(
                        SafetyViolation(
                            rule="UNSAFE_OS_CALL",
                            message=f"Prohibited system call 'os.{attr_name}()'.",
                            line_number=node.lineno,
                            severity=Severity.CRITICAL,
                        )
                    )
                elif caller_name == "subprocess":
                    self.violations.append(
                        SafetyViolation(
                            rule="SUBPROCESS_CALL",
                            message=f"Prohibited subprocess call 'subprocess.{attr_name}()'.",
                            line_number=node.lineno,
                            severity=Severity.CRITICAL,
                        )
                    )

        # Check string arguments for blocked host patterns (e.g. AWS metadata 169.254.169.254)
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                for blocked in BLOCKED_HOST_PATTERNS:
                    if blocked in arg.value:
                        self.violations.append(
                            SafetyViolation(
                                rule="MALICIOUS_DESTINATION_URL",
                                message=f"Suspicious / blocked destination host detected: '{blocked}'.",
                                line_number=node.lineno,
                                severity=Severity.CRITICAL,
                            )
                        )

        self.generic_visit(node)


class SafetyScanner:
    """Static AST analyzer that verifies generated code safety before execution."""

    @classmethod
    def scan(cls, code: str) -> SafetyReport:
        """Parse and scan Python code for security violations."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return SafetyReport(
                is_safe=False,
                violations=[
                    SafetyViolation(
                        rule="SYNTAX_ERROR",
                        message=f"Syntax error prevents safety analysis: {e}",
                        line_number=e.lineno,
                        severity=Severity.CRITICAL,
                    )
                ],
            )

        visitor = SafetyVisitor()
        visitor.visit(tree)

        is_safe = len([v for v in visitor.violations if v.severity in (Severity.CRITICAL, Severity.HIGH)]) == 0

        return SafetyReport(
            is_safe=is_safe,
            violations=visitor.violations,
            warnings=visitor.warnings,
        )
