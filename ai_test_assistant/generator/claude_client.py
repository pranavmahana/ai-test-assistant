"""Anthropic Claude API client for API test generation."""

import os
import re
from typing import List, Optional

from ai_test_assistant.config import DEFAULT_CLAUDE_MODEL
from ai_test_assistant.generator.prompt_builder import PromptBuilder
from ai_test_assistant.parser.models import EndpointChunk


class ClaudeTestGenerator:
    """Generates pytest suites using the Anthropic Claude Messages API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_CLAUDE_MODEL,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = os.getenv("ANTHROPIC_MODEL", model)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None

    @property
    def client(self):
        """Lazy initialization of the Anthropic SDK client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "Anthropic API key not found. Please provide api_key or set ANTHROPIC_API_KEY."
                )
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "The 'anthropic' package is required. Install it via 'pip install anthropic'."
                )
        return self._client

    def generate(
        self,
        chunks: List[EndpointChunk],
        query: Optional[str] = None,
        base_url: str = "http://localhost:8000",
    ) -> str:
        """Invoke Claude to generate a pytest suite for the provided endpoint chunks."""
        if not chunks:
            raise ValueError("Cannot generate tests without at least one endpoint chunk.")

        system_prompt = PromptBuilder.build_system_prompt()
        user_prompt = PromptBuilder.build_user_prompt(chunks, query=query, base_url=base_url)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
        )

        raw_output = response.content[0].text
        return self.extract_code(raw_output)

    @classmethod
    def extract_code(cls, response_text: str) -> str:
        """Extract executable Python code from markdown code fences or raw text."""
        # Search for ```python ... ```
        pattern = r"```(?:python)?\s*\n(.*?)```"
        matches = re.findall(pattern, response_text, re.DOTALL)
        if matches:
            # Pick the largest python block
            return max(matches, key=len).strip()

        # Fallback: if no backticks found, return clean text
        return response_text.strip()
