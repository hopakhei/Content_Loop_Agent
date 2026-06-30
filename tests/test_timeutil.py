from datetime import datetime
from zoneinfo import ZoneInfo

from core.timeutil import nearest_slot, parse_notion_datetime, slot_to_minutes

SLOTS = ["07:30", "10:00", "12:30", "18:30", "21:30"]
HKT = ZoneInfo("Asia/Hong_Kong")


def test_slot_to_minutes():
    assert slot_to_minutes("07:30") == 450
    assert slot_to_minutes("21:30") == 1290


def test_parse_date_only_is_hkt():
    dt = parse_notion_datetime("2026-06-30")
    assert dt.tzinfo is not None
    assert (dt.year, dt.month, dt.day) == (2026, 6, 30)


def test_parse_datetime_offset():
    dt = parse_notion_datetime("2026-06-30T07:30:00+08:00")
    assert dt.hour == 7 and dt.minute == 30


def test_parse_datetime_utc_z_converted_to_hkt():
    dt = parse_notion_datetime("2026-06-30T00:00:00Z")  # 00:00 UTC == 08:00 HKT
    assert dt.hour == 8


def test_nearest_slot():
    assert nearest_slot(datetime(2026, 6, 30, 12, 40, tzinfo=HKT), SLOTS) == "12:30"
    assert nearest_slot(datetime(2026, 6, 30, 22, 0, tzinfo=HKT), SLOTS) == "21:30"
    assert nearest_slot(datetime(2026, 6, 30, 7, 20, tzinfo=HKT), SLOTS) == "07:30"
