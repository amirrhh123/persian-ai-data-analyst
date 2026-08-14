import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.semantic.lifecycle_service import semantic_lifecycle_service


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether the active semantic layer matches the current database fingerprint."
    )
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--sample-size", type=int, default=3)
    parser.add_argument("--sample-value-limit", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = semantic_lifecycle_service.check_freshness(
        tenant_id=args.tenant_id,
        sample_size=args.sample_size,
        sample_value_limit=args.sample_value_limit,
    )

    if args.json:
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    else:
        print(f"status: {result.status}")
        print(f"tenant_id: {result.tenant_id}")
        print(f"tables: {result.tables_discovered}")
        print(f"relationships: {result.relationships_found}")
        print(f"current_fingerprint: {result.current_fingerprint}")
        print(f"stored_fingerprint: {result.stored_fingerprint}")
        print(f"message: {result.message}")
        print(f"recommended_action: {result.recommended_action}")

    return 0 if result.status == "up_to_date" else 2


if __name__ == "__main__":
    raise SystemExit(main())
