"""Command-line entry point for rebuilding the router dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.router.dataset_builder import build_router_dataset


def main() -> int:
    """Build the dataset and print stable result counts."""
    parser = argparse.ArgumentParser(description="Build Persian intent-router datasets.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    result = build_router_dataset(args.repo_root, args.output_dir)
    print(f"raw={result.raw_count}")
    print(f"reviewed={result.reviewed_count}")
    print(f"output={result.raw_path.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
