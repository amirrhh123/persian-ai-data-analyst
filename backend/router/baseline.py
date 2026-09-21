"""Offline baseline evaluation for the pre-ML domain router."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from backend.pipeline.intent import extract_intent
from backend.router.labels import V1_DOMAINS
from backend.semantic.loader import load_tenant_semantic_catalog
from backend.semantic.models import SemanticCatalog


BASELINE_SCHEMA_VERSION = "router-baseline-v1"
ENTITY_DOMAIN_MAP = {
    "student": "student",
    "employee": "employee",
    "school": "school",
    "salary": "salary",
    "organization": "organization",
    "organization_unit": "organization",
    "retirement": "retirement",
}


@dataclass(frozen=True)
class BaselineRoute:
    """Observable outcome of one pre-model routing decision."""

    domain: str
    fallback: bool
    embedding_calls: int = 0
    llm_calls: int = 0


RouteFunction = Callable[[str], BaselineRoute]
ClockFunction = Callable[[], int]


def create_current_rule_router(
    semantic_catalog: SemanticCatalog | None = None,
) -> RouteFunction:
    """Create the current deterministic intent route with no model calls."""
    catalog = semantic_catalog or load_tenant_semantic_catalog()

    def route(text: str) -> BaselineRoute:
        intent = extract_intent(text, catalog)
        domain = ENTITY_DOMAIN_MAP.get(intent.requested_entity or "", "generic_semantic")
        return BaselineRoute(
            domain=domain,
            fallback=domain == "generic_semantic",
            embedding_calls=0,
            llm_calls=0,
        )

    return route


def load_reviewed_examples(path: Path) -> list[dict[str, object]]:
    """Load and validate reviewed JSONL examples."""
    examples: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {line_number}") from exc
        text = item.get("text")
        label = item.get("label")
        reviewed = item.get("reviewed")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"invalid text at line {line_number}")
        if label not in V1_DOMAINS:
            raise ValueError(f"invalid label at line {line_number}: {label}")
        if reviewed is not True:
            raise ValueError(f"non-reviewed example at line {line_number}")
        examples.append(item)
    if not examples:
        raise ValueError("reviewed dataset is empty")
    return examples


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def evaluate_router_baseline(
    examples: Iterable[dict[str, object]],
    route: RouteFunction,
    *,
    clock_ns: ClockFunction = time.perf_counter_ns,
) -> dict[str, object]:
    """Evaluate accuracy, latency, calls, fallback, and per-class errors."""
    rows = list(examples)
    if not rows:
        raise ValueError("examples must not be empty")

    correct = 0
    fallback_count = 0
    embedding_calls = 0
    llm_calls = 0
    latencies_ms: list[float] = []
    supports: Counter[str] = Counter()
    class_correct: Counter[str] = Counter()
    predictions: dict[str, Counter[str]] = defaultdict(Counter)
    errors: dict[str, list[dict[str, str]]] = defaultdict(list)

    for item in rows:
        text = str(item["text"])
        expected = str(item["label"])
        started = clock_ns()
        outcome = route(text)
        elapsed_ms = (clock_ns() - started) / 1_000_000
        if outcome.domain not in V1_DOMAINS:
            raise ValueError(f"router returned unsupported domain: {outcome.domain}")

        supports[expected] += 1
        predictions[expected][outcome.domain] += 1
        fallback_count += int(outcome.fallback)
        embedding_calls += outcome.embedding_calls
        llm_calls += outcome.llm_calls
        latencies_ms.append(elapsed_ms)
        if outcome.domain == expected:
            correct += 1
            class_correct[expected] += 1
        else:
            errors[expected].append(
                {"text": text, "expected": expected, "predicted": outcome.domain}
            )

    total = len(rows)
    per_class: dict[str, dict[str, object]] = {}
    for label in sorted(V1_DOMAINS):
        support = supports[label]
        per_class[label] = {
            "support": support,
            "correct": class_correct[label],
            "errors": support - class_correct[label],
            "accuracy": round(class_correct[label] / support, 6) if support else None,
            "predictions": dict(sorted(predictions[label].items())),
            "error_examples": errors[label],
        }

    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "router": "current_deterministic_intent_rules",
        "samples": total,
        "accuracy": round(correct / total, 6),
        "correct": correct,
        "errors": total - correct,
        "fallback": {
            "count": fallback_count,
            "rate": round(fallback_count / total, 6),
        },
        "calls": {
            "embedding": embedding_calls,
            "llm": llm_calls,
            "embedding_per_question": round(embedding_calls / total, 6),
            "llm_per_question": round(llm_calls / total, 6),
        },
        "latency_ms": {
            "mean": round(sum(latencies_ms) / total, 6),
            "p50": round(_percentile(latencies_ms, 0.50), 6),
            "p95": round(_percentile(latencies_ms, 0.95), 6),
            "max": round(max(latencies_ms), 6),
        },
        "per_class": per_class,
    }


def run_baseline(
    dataset_path: Path,
    output_path: Path,
    *,
    route: RouteFunction | None = None,
) -> dict[str, object]:
    """Run the baseline and persist a self-identifying JSON report."""
    dataset_bytes = dataset_path.read_bytes()
    examples = load_reviewed_examples(dataset_path)
    report = evaluate_router_baseline(examples, route or create_current_rule_router())
    report["dataset"] = {
        "path": dataset_path.name,
        "sha256": hashlib.sha256(dataset_bytes).hexdigest(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
