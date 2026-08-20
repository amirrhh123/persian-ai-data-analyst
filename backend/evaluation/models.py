from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvaluationResult:
    metrics: dict[str, float]
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)

