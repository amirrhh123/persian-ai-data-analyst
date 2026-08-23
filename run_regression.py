import argparse
import json
import sys

from tests.benchmark.regression import run_sync, save_results, summarize


def _force_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(description="Run SQL regression benchmark.")
    parser.add_argument("--case-id", action="append", dest="case_ids", default=None)
    parser.add_argument("--category", action="append", dest="categories", default=None)
    parser.add_argument("--priority", action="append", dest="priorities", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-pass-rate", type=float, default=100.0)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    outcomes = run_sync(
        case_ids=args.case_ids,
        categories=args.categories,
        priorities=args.priorities,
        limit=args.limit,
    )
    summary = summarize(outcomes, min_pass_rate=args.min_pass_rate)
    timestamped = latest = None
    if not args.no_save:
        timestamped, latest = save_results(outcomes, min_pass_rate=args.min_pass_rate)

    payload = {
        "summary": summary,
        "results": [outcome.to_dict() for outcome in outcomes],
        "output_path": str(timestamped) if timestamped else None,
        "latest_path": str(latest) if latest else None,
    }

    if args.as_json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"status: {summary['status']}")
        print(f"passed: {summary['passed']}/{summary['total']}")
        print(f"failed: {summary['failed']}")
        print(f"pass_rate: {summary['pass_rate']}%")
        print(f"min_pass_rate: {summary['min_pass_rate']}%")
        print(f"avg_elapsed_ms: {summary['avg_elapsed_ms']}")
        if latest:
            print(f"latest: {latest}")
        if timestamped:
            print(f"saved: {timestamped}")
        for outcome in outcomes:
            status = "PASS" if outcome.passed else "FAIL"
            print(f"[{status}] {outcome.id} category={outcome.category} priority={outcome.priority} elapsed={outcome.elapsed_ms:.0f}ms")
            for failure in outcome.failures:
                print(f"  - {failure}")

    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
