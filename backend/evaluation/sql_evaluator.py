import re
from .models import EvaluationResult


def _normalise(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).lower()


def evaluate_sql(generated: str, expected: str, execution_correct: bool | None = None) -> EvaluationResult:
    exact = float(_normalise(generated) == _normalise(expected))
    metrics = {"sql_exact_match": exact}
    if execution_correct is not None:
        metrics["sql_execution_accuracy"] = float(execution_correct)
    return EvaluationResult(metrics, exact == 1.0, {"generated": generated, "expected": expected})

