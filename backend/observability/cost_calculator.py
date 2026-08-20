from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_per_1k: float = 0.0
    output_per_1k: float = 0.0


def estimate_cost(input_tokens: int, output_tokens: int, pricing: ModelPricing) -> float:
    return (input_tokens / 1000 * pricing.input_per_1k) + (output_tokens / 1000 * pricing.output_per_1k)

