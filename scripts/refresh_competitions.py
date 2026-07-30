"""CLI entry point used by GitHub Actions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.refresh_service import RefreshService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--trigger", default="manual", choices=["manual", "scheduled"])
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    with (PROJECT_ROOT / "config" / "config.yaml").open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    result = RefreshService(config).run(job_id=args.job_id, trigger_type=args.trigger)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in {"completed", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
