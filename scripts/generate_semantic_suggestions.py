import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.semantic.suggestion_service import semantic_suggestion_service


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Generate draft semantic suggestions from discovery.json.")
    parser.add_argument("--tenant-id", default=settings.tenant_id)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    suggestions, output_path = semantic_suggestion_service.sync(
        tenant_id=args.tenant_id,
        output_path=args.output,
    )

    print("status: success")
    print(f"tenant_id: {suggestions.tenant_id}")
    print(f"source_fingerprint: {suggestions.source_fingerprint}")
    print(f"tables: {len(suggestions.tables)}")
    print(f"joins: {len(suggestions.joins)}")
    print(f"business_terms: {len(suggestions.business_terms)}")
    print(f"value_mappings: {len(suggestions.value_mappings)}")
    print(f"rules: {len(suggestions.rules)}")
    print(f"output_path: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
