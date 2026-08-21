"""Run R10 retrieval benchmark and optionally save its JSON report."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.retrieval_benchmark.service import retrieval_benchmark_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Persian retrieval quality benchmark")
    parser.add_argument("--tenant", default="education_ministry")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--minimum-top1", type=float, default=0.80)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("tests/results/retrieval_benchmark.json"))
    args = parser.parse_args()

    result = retrieval_benchmark_service.run(
        args.tenant, top_k=args.top_k, minimum_top1=args.minimum_top1,
        dataset_path=args.dataset,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"status={result.status} top1={result.overall_top1_accuracy:.2%} output={args.output}")
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
