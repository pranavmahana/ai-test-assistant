"""Configuration settings and constants for AI Test Assistant."""

from dataclasses import dataclass
from typing import Dict, List, Set


@dataclass
class EvaluationWeights:
    """Weights for the composite evaluation score (must sum to 100)."""
    syntax_validity: float = 20.0
    assertion_quality: float = 20.0
    hallucination_penalty: float = 25.0
    endpoint_coverage: float = 20.0
    negative_test_presence: float = 15.0

    def validate(self) -> None:
        total = (
            self.syntax_validity
            + self.assertion_quality
            + self.hallucination_penalty
            + self.endpoint_coverage
            + self.negative_test_presence
        )
        if round(total, 2) != 100.0:
            raise ValueError(f"Evaluation weights must sum to 100, got {total}")


# Default evaluation rubric weights
DEFAULT_WEIGHTS = EvaluationWeights()

# Default Anthropic Claude model
DEFAULT_CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
FALLBACK_CLAUDE_MODEL = "claude-3-haiku-20240307"

# AST Safety Scanner Disallowed Modules & Functions
DANGEROUS_MODULES: Set[str] = {
    "os",
    "subprocess",
    "sys",
    "shutil",
    "pty",
    "ctypes",
    "socket",
    "pickle",
    "builtins",
    "importlib",
    "posix",
    "nt",
    "_thread",
    "threading",
    "multiprocessing",
    "signal",
}

DANGEROUS_FUNCTIONS: Set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "globals",
    "locals",
    "getattr",
    "setattr",
    "delattr",
    "open",  # Restrict arbitrary file operations
}

ALLOWED_HTTP_LIBRARIES: Set[str] = {
    "requests",
    "httpx",
    "urllib3",
    "pytest",
    "json",
    "uuid",
    "datetime",
    "time",
    "math",
    "typing",
    "re",
}

# Suspicious IP addresses / external hosts that generated tests must NEVER call
BLOCKED_HOST_PATTERNS: List[str] = [
    "169.254.169.254",  # AWS/Cloud metadata service
    "metadata.google.internal",
    "100.100.100.200",  # Alibaba metadata
    "evil.com",
    "attacker.com",
    "webhook.site",
    "burpcollaborator.net",
    "canarytokens.com",
]

# Prompt injection marker tags
UNTRUSTED_DATA_START_TAG = "<untrusted_spec_data>"
UNTRUSTED_DATA_END_TAG = "</untrusted_spec_data>"
