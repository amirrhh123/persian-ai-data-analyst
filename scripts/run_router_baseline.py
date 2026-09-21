"""Run and persist the pre-model router baseline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.router.baseline import run_baseline


def main() -> int:
    """Evaluate current deterministic routing against reviewed data."""
    parser = argparse.ArgumentParser(description="Measure the pre-ML routing baseline.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "training" / "router" / "dataset_reviewed.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "training" / "router" / "baseline.json",
    )
    args = parser.parse_args()
    report = run_baseline(args.dataset.resolve(), args.output.resolve())
    print(f"samples={report['samples']}")
    print(f"accuracy={report['accuracy']}")
    print(f"fallback_rate={report['fallback']['rate']}")
    print(f"embedding_calls={report['calls']['embedding']}")
    print(f"llm_calls={report['calls']['llm']}")
    print(f"output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

