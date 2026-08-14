import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.semantic.benchmark_service import semantic_benchmark_service


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run semantic quality gate benchmark.")
    parser.add_argument("--tenant-id", default=settings.tenant_id)
    parser.add_argument("--min-pass-rate", type=float, default=95.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case-id", action="append", dest="case_ids", default=None)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    response = semantic_benchmark_service.run_sync(
        tenant_id=args.tenant_id,
        min_pass_rate=args.min_pass_rate,
        case_ids=args.case_ids,
        limit=args.limit,
        save=not args.no_save,
    )

    if args.as_json:
        print(json.dumps(response.model_dump(mode="json"), ensure_ascii=True, indent=2))
    else:
        summary = response.summary
        print(f"status: {response.status}")
        print(f"tenant_id: {response.tenant_id}")
        print(f"source_fingerprint: {response.source_fingerprint}")
        print(f"passed: {summary.passed}/{summary.total}")
        print(f"failed: {summary.failed}")
        print(f"pass_rate: {summary.pass_rate}%")
        print(f"min_pass_rate: {summary.min_pass_rate}%")
        print(f"avg_elapsed_ms: {summary.avg_elapsed_ms}")
        print(f"output_path: {response.output_path}")
        for item in response.results:
            if not item.passed:
                print(f"[FAIL] {item.id}")
                for failure in item.failures:
                    print(f"  - {failure}")

    return 0 if response.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
