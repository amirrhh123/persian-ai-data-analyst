from .answer_evaluator import evaluate_answer
from .models import EvaluationResult
from .retrieval_evaluator import evaluate_retrieval
from .safety_evaluator import evaluate_safety
from .sql_evaluator import evaluate_sql


def run_evaluation(*, expected_retrieval: list[str] | None = None, ranked_retrieval: list[str] | None = None,
                   generated_sql: str | None = None, expected_sql: str | None = None,
                   answer: str | None = None, reference_answer: str | None = None,
                   rejected: bool | None = None, unsafe: bool = True,
                   sql_execution_correct: bool | None = None) -> EvaluationResult:
    metrics: dict[str, float] = {}
    details = {}
    if expected_retrieval is not None and ranked_retrieval is not None:
        result = evaluate_retrieval(expected_retrieval, ranked_retrieval); metrics.update(result.metrics)
    if generated_sql is not None and expected_sql is not None:
        result = evaluate_sql(generated_sql, expected_sql, sql_execution_correct); metrics.update(result.metrics)
    if answer is not None and reference_answer is not None:
        result = evaluate_answer(answer, reference_answer); metrics.update(result.metrics)
    if rejected is not None:
        result = evaluate_safety(rejected, unsafe); metrics.update(result.metrics)
    return EvaluationResult(metrics, all(value >= 0.5 for value in metrics.values()), details)

