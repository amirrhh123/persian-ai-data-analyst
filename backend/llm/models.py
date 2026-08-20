from dataclasses import dataclass


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ContextFitResult:
    text: str
    original_tokens: int
    final_tokens: int
    truncated: bool

