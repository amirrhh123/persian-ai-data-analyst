import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.database.discovery_service import schema_discovery_service


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Discover live PostgreSQL schema metadata.")
    parser.add_argument("--tenant-id", default=settings.tenant_id)
    parser.add_argument("--schema-name", default="public")
    parser.add_argument("--sample-size", type=int, default=3)
    parser.add_argument("--sample-value-limit", type=int, default=8)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    result = schema_discovery_service.sync_discovery(
        tenant_id=args.tenant_id,
        schema_name=args.schema_name,
        sample_size=args.sample_size,
        sample_value_limit=args.sample_value_limit,
        output_path=args.output,
    )

    print(f"status: {result.status}")
    print(f"tenant_id: {result.tenant_id}")
    print(f"tables_discovered: {result.tables_discovered}")
    print(f"relationships_found: {result.relationships_found}")
    print(f"fingerprint: {result.fingerprint}")
    print(f"output_path: {result.output_path}")

    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
