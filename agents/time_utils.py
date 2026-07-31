"""Project-wide timezone helpers."""

from datetime import datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    """Return an aware datetime in the project's display/write timezone."""
    return datetime.now(BEIJING_TZ)


def beijing_now_iso() -> str:
    """Return an ISO-8601 Beijing timestamp, including the +08:00 offset."""
    return beijing_now().isoformat()
