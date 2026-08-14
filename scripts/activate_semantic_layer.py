import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.semantic.activation_service import semantic_activation_service
from backend.semantic.benchmark_service import semantic_benchmark_service


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Validate and activate semantic_suggestions.json.")
    parser.add_argument("--tenant-id", default=settings.tenant_id)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--min-pass-rate", type=float, default=95.0)
    parser.add_argument("--benchmark-limit", type=int, default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if args.validate_only:
        result = semantic_activation_service.validate_current(args.tenant_id)
    else:
        result = semantic_activation_service.activate(args.tenant_id, force=args.force)

    benchmark_status = None
    if args.as_json:
        payload = {"activation": result.model_dump(mode="json")}
        if args.benchmark and result.status not in {"blocked", "invalid"}:
            benchmark = semantic_benchmark_service.run_sync(
                tenant_id=args.tenant_id,
                min_pass_rate=args.min_pass_rate,
                limit=args.benchmark_limit,
            )
            benchmark_status = benchmark.status
            payload["benchmark"] = benchmark.model_dump(mode="json")
        print(json.dumps(payload if args.benchmark else result.model_dump(mode="json"), ensure_ascii=True, indent=2))
    else:
        print(f"status: {result.status}")
        print(f"tenant_id: {result.tenant_id}")
        print(f"source_fingerprint: {result.source_fingerprint}")
        print(f"active_catalog_path: {result.active_catalog_path}")
        print(f"tables: {result.tables}")
        print(f"joins: {result.joins}")
        print(f"rules: {result.rules}")
        print(f"issues: {len(result.issues)}")
        for issue in result.issues:
            print(f"- {issue.severity} {issue.code}: {issue.message} ({issue.path})")

        if args.benchmark and result.status not in {"blocked", "invalid"}:
            benchmark = semantic_benchmark_service.run_sync(
                tenant_id=args.tenant_id,
                min_pass_rate=args.min_pass_rate,
                limit=args.benchmark_limit,
            )
            benchmark_status = benchmark.status
            print("")
            print(f"benchmark_status: {benchmark.status}")
            print(f"benchmark_passed: {benchmark.summary.passed}/{benchmark.summary.total}")
            print(f"benchmark_pass_rate: {benchmark.summary.pass_rate}%")
            print(f"benchmark_output_path: {benchmark.output_path}")

    if result.status in {"blocked", "invalid"}:
        return 1
    if benchmark_status == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
