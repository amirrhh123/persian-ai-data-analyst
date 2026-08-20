from .models import EvaluationResult


def evaluate_retrieval(expected: list[str], ranked: list[str]) -> EvaluationResult:
    expected_set = set(expected)
    hit = bool(ranked and ranked[0] in expected_set)
    reciprocal_rank = next((1 / (i + 1) for i, item in enumerate(ranked) if item in expected_set), 0.0)
    metrics = {"retrieval_top1": float(hit), "retrieval_mrr": reciprocal_rank}
    return EvaluationResult(metrics, hit, {"expected": expected, "ranked": ranked})

