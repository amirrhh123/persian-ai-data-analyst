import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.semantic.activation_service import semantic_activation_service


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="List or rollback semantic layer versions.")
    parser.add_argument("--tenant-id", default=settings.tenant_id)
    parser.add_argument("--list", action="store_true", dest="list_versions")
    parser.add_argument("--version-id", default="")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if args.list_versions:
        versions = semantic_activation_service.list_versions(args.tenant_id)
        if args.as_json:
            print(json.dumps([item.model_dump(mode="json") for item in versions], ensure_ascii=True, indent=2))
        else:
            if not versions:
                print("No semantic versions found.")
            for item in versions:
                print(f"{item.version_id} | tables={item.tables} joins={item.joins} rules={item.rules} | {item.path}")
        return 0

    if not args.version_id:
        print("Provide --version-id or use --list.")
        return 1

    result = semantic_activation_service.rollback(args.version_id, args.tenant_id)
    if args.as_json:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=True, indent=2))
    else:
        print(f"status: {result.status}")
        print(f"tenant_id: {result.tenant_id}")
        print(f"restored_version_id: {result.restored_version_id}")
        print(f"active_catalog_path: {result.active_catalog_path}")
        print(f"backup_path: {result.backup_path}")
        print(f"message: {result.message}")

    return 0 if result.status == "rolled_back" else 1


if __name__ == "__main__":
    raise SystemExit(main())
