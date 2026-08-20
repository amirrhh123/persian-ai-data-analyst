from .models import EvaluationResult


def evaluate_answer(answer: str, reference: str, grounded: bool | None = None) -> EvaluationResult:
    overlap = bool(answer.strip() and reference.strip() and any(w in answer for w in reference.split() if len(w) > 2))
    groundedness = float(grounded if grounded is not None else overlap)
    return EvaluationResult({"answer_groundedness": groundedness}, groundedness >= 0.5)

