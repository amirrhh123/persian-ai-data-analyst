from __future__ import annotations

import re
from typing import Protocol


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class ApproximateTokenCounter:
    """Dependency-free estimate used when the target tokenizer is unavailable."""

    def count(self, text: str) -> int:
        if not text:
            return 0
        pieces = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
        return max(1, len(pieces))


class HuggingFaceTokenCounter:
    def __init__(self, model_path: str):
        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)

    def count(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=True))


def create_token_counter(model_path: str | None = None) -> TokenCounter:
    if model_path:
        try:
            return HuggingFaceTokenCounter(model_path)
        except Exception:
            pass
    return ApproximateTokenCounter()

