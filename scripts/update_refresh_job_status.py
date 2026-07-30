"""Update a dispatched refresh job before project dependencies are installed."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"running", "failed"}:
        raise SystemExit("usage: update_refresh_job_status.py running|failed")

    status = sys.argv[1]
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    job_id = os.getenv("JOB_ID", "").strip()
    if not url or not key or not job_id:
        raise RuntimeError(
            "SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and JOB_ID are required"
        )

    values: dict[str, str] = {"status": status}
    if status == "failed":
        values.update({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error_message": (
                "GitHub Actions failed before the refresh script started."
            ),
        })

    endpoint = (
        f"{url}/rest/v1/refresh_jobs?"
        + urllib.parse.urlencode({"id": f"eq.{job_id}"})
    )
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(values).encode("utf-8"),
        headers={
            "apikey": key,
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="PATCH",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status not in {200, 204}:
            raise RuntimeError(
                f"Supabase status update returned {response.status}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
