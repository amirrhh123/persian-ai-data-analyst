"""Tests for the pre-model routing baseline metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.router.baseline import (
    BaselineRoute,
    evaluate_router_baseline,
    load_reviewed_examples,
    run_baseline,
)


def _examples() -> list[dict[str, object]]:
    return [
        {"text": "تعداد دانش آموزان", "label": "student", "reviewed": True},
        {"text": "اطلاعات کارمندان", "label": "employee", "reviewed": True},
        {"text": "مدارس تهران", "label": "school", "reviewed": True},
    ]


def test_baseline_reports_accuracy_calls_fallback_latency_and_class_errors() -> None:
    outcomes = iter(
        [
            BaselineRoute("student", False, embedding_calls=1),
            BaselineRoute("generic_semantic", True, llm_calls=1),
            BaselineRoute("school", False, embedding_calls=1),
        ]
    )
    times = iter([0, 1_000_000, 2_000_000, 4_000_000, 5_000_000, 8_000_000])
    report = evaluate_router_baseline(
        _examples(),
        lambda _text: next(outcomes),
        clock_ns=lambda: next(times),
    )

    assert report["accuracy"] == 0.666667
    assert report["fallback"] == {"count": 1, "rate": 0.333333}
    assert report["calls"]["embedding"] == 2
    assert report["calls"]["llm"] == 1
    assert report["latency_ms"] == {"mean": 2.0, "p50": 2.0, "p95": 3.0, "max": 3.0}
    employee = report["per_class"]["employee"]
    assert employee["errors"] == 1
    assert employee["error_examples"][0]["predicted"] == "generic_semantic"


def test_empty_or_invalid_datasets_are_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_reviewed_examples(empty)

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text(
        json.dumps({"text": "سؤال", "label": "unsafe", "reviewed": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid label"):
        load_reviewed_examples(invalid)


def test_non_reviewed_example_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "data.jsonl"
    path.write_text(
        json.dumps({"text": "اطلاعات مدرسه", "label": "school", "reviewed": False}, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-reviewed"):
        load_reviewed_examples(path)


def test_unsupported_router_domain_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported domain"):
        evaluate_router_baseline(
            _examples()[:1],
            lambda _text: BaselineRoute("unsafe", False),
        )


def test_run_baseline_persists_dataset_hash(tmp_path: Path) -> None:
    dataset = tmp_path / "reviewed.jsonl"
    dataset.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in _examples()) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "baseline.json"
    report = run_baseline(
        dataset,
        output,
        route=lambda text: BaselineRoute(
            "student" if "دانش" in text else "employee" if "کارمند" in text else "school",
            False,
        ),
    )

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert report["accuracy"] == 1.0
    assert persisted["dataset"]["sha256"]
    assert persisted["calls"] == {
        "embedding": 0,
        "embedding_per_question": 0.0,
        "llm": 0,
        "llm_per_question": 0.0,
    }

