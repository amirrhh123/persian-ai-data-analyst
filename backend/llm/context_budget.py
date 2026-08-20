from __future__ import annotations

from dataclasses import dataclass

from .models import ContextFitResult
from .token_counter import TokenCounter


@dataclass(frozen=True)
class ContextBudget:
    maximum_tokens: int
    reserved_output_tokens: int
    truncation_marker: str = "\n...[context trimmed]...\n"

    def __post_init__(self) -> None:
        if self.maximum_tokens <= 0 or self.reserved_output_tokens < 0:
            raise ValueError("Context token limits must be positive")
        if self.reserved_output_tokens >= self.maximum_tokens:
            raise ValueError("Reserved output tokens must be below the context maximum")

    @property
    def available_input_tokens(self) -> int:
        return self.maximum_tokens - self.reserved_output_tokens

    def fit(self, text: str, counter: TokenCounter) -> ContextFitResult:
        original = counter.count(text)
        if original <= self.available_input_tokens:
            return ContextFitResult(text, original, original, False)
        words = text.split()
        marker = self.truncation_marker
        if counter.count(marker) > self.available_input_tokens:
            marker = "..."
        if counter.count(marker) > self.available_input_tokens:
            marker = ""
        lo, hi = 0, len(words)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            candidate = " ".join(words[:mid]) + marker
            if counter.count(candidate) <= self.available_input_tokens:
                lo = mid
            else:
                hi = mid - 1
        fitted = " ".join(words[:lo]) + marker
        return ContextFitResult(fitted, original, counter.count(fitted), True)
