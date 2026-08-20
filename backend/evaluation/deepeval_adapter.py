from typing import Any


def evaluate_with_deepeval(test_cases: list[Any]) -> Any:
    """Optional adapter; SQL-specific internal evaluators remain authoritative."""
    try:
        from deepeval import evaluate
    except ImportError as exc:
        raise RuntimeError("Install deepeval to use this optional adapter") from exc
    return evaluate(test_cases)
