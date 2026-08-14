import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.semantic.lifecycle_service import semantic_lifecycle_service


async def run(args: argparse.Namespace) -> int:
    result = await semantic_lifecycle_service.ensure_updated(
        tenant_id=args.tenant_id,
        min_pass_rate=args.min_pass_rate,
        benchmark_limit=args.benchmark_limit,
        force_activate=args.force_activate,
    )

    if args.json:
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    else:
        print(f"status: {result.status}")
        print(f"action: {result.action}")
        print(f"tenant_id: {result.tenant_id}")
        print(f"freshness_before: {result.freshness_before.status}")
        if result.lifecycle:
            print(f"lifecycle: {result.lifecycle.status}")
        if result.freshness_after:
            print(f"freshness_after: {result.freshness_after.status}")
        print(f"message: {result.message}")

    return 0 if result.status in {"skipped", "updated"} else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely update the semantic layer only when the database fingerprint changed."
    )
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--min-pass-rate", type=float, default=95.0)
    parser.add_argument("--benchmark-limit", type=int, default=None)
    parser.add_argument("--force-activate", action="store_true")
    parser.add_argument("--json", action="store_true")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
