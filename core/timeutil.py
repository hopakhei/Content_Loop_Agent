"""Timezone-aware helpers (everything is reasoned about in HKT)."""
from __future__ import annotations

from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo


def tz(name: str = "Asia/Hong_Kong") -> ZoneInfo:
    return ZoneInfo(name)


def now(name: str = "Asia/Hong_Kong") -> datetime:
    return datetime.now(tz(name))


def parse_notion_datetime(value: str, tzname: str = "Asia/Hong_Kong") -> datetime:
    """Parse a Notion date `start` string into a tz-aware datetime in `tzname`.

    Handles both date-only ("2026-06-30") and datetime ("2026-06-30T07:30:00+08:00"
    or trailing "Z") values. Naive values are assumed to already be in `tzname`.
    """
    raw = value.replace("Z", "+00:00") if value.endswith("Z") else value
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz(tzname))
    return dt.astimezone(tz(tzname))


def slot_to_minutes(slot: str) -> int:
    """'07:30' -> 450 (minutes since midnight)."""
    hh, mm = slot.split(":")
    return int(hh) * 60 + int(mm)


def slot_to_time(slot: str) -> time:
    hh, mm = slot.split(":")
    return time(int(hh), int(mm))


def nearest_slot(current: datetime, slots: list[str]) -> Optional[str]:
    """The configured slot closest to `current`'s wall-clock time."""
    if not slots:
        return None
    cur = current.hour * 60 + current.minute
    return min(slots, key=lambda s: abs(cur - slot_to_minutes(s)))
