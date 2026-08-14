import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.semantic.lifecycle_service import semantic_lifecycle_service


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run full semantic update lifecycle.")
    parser.add_argument("--tenant-id", default=settings.tenant_id)
    parser.add_argument("--schema-name", default="public")
    parser.add_argument("--sample-size", type=int, default=3)
    parser.add_argument("--sample-value-limit", type=int, default=8)
    parser.add_argument("--min-pass-rate", type=float, default=95.0)
    parser.add_argument("--benchmark-limit", type=int, default=None)
    parser.add_argument("--force-activate", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    response = semantic_lifecycle_service.run_sync(
        tenant_id=args.tenant_id,
        schema_name=args.schema_name,
        sample_size=args.sample_size,
        sample_value_limit=args.sample_value_limit,
        min_pass_rate=args.min_pass_rate,
        benchmark_limit=args.benchmark_limit,
        force_activate=args.force_activate,
    )

    if args.as_json:
        print(json.dumps(response.model_dump(mode="json"), ensure_ascii=True, indent=2))
    else:
        print(f"status: {response.status}")
        print(f"tenant_id: {response.tenant_id}")
        print(f"source_fingerprint: {response.source_fingerprint}")
        for step in response.steps:
            print(f"[{step.status}] {step.name}: {step.message}")
            if step.output_path:
                print(f"  output_path: {step.output_path}")
        if response.benchmark:
            summary = response.benchmark.summary
            print(f"benchmark: {summary.passed}/{summary.total} passed ({summary.pass_rate}%)")
            print(f"benchmark_gate: {summary.gate_status}")

    return 0 if response.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
