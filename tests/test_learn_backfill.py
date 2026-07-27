"""Free-read platforms recover from a night the API was down.

Metrics are read once per post, in the [24h, 48h) window, because an X read
costs the same monthly credit as a write. Meta charges nothing for Threads or
Instagram insights, so applying the same restraint there just meant a bad night
lost the data permanently — while the Threads token was 500-ing in mid-July,
every post whose one window fell in that stretch kept a null forever, and seven
of fourteen Threads rows still read zero.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from loops import learn_loop as L


def _row(pid: str, platform: str, hours_old: float, impressions: float) -> dict:
    posted = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    return {"post_id": pid, "platform": platform, "impressions": impressions,
            "posted_at": posted.isoformat()}


class _Recorder:
    def __init__(self):
        self.asked: list[str] = []

    def get_insights(self, ids):
        self.asked = list(ids)
        return {}

    get_metrics = get_insights


def _refresh(rows):
    threads, x = _Recorder(), _Recorder()
    L._refresh_metrics(rows, None, x, threads, None, logging.getLogger("t"), dry_run=False)
    return sorted(threads.asked), sorted(x.asked)


def test_blank_threads_row_past_its_window_is_retried():
    th, _ = _refresh([_row("stranded", "Threads", 96, 0)])
    assert th == ["stranded"]


def test_threads_row_that_already_has_numbers_is_not_reread():
    th, _ = _refresh([_row("done", "Threads", 96, 6401)])
    assert th == []


def test_threads_row_younger_than_the_window_waits():
    th, _ = _refresh([_row("fresh", "Threads", 5, 0)])
    assert th == []


def test_backfill_gives_up_after_the_cap():
    th, _ = _refresh([_row("ancient", "Threads", L.BACKFILL_MAX_AGE_HOURS + 10, 0)])
    assert th == []


def test_x_still_gets_exactly_one_read():
    """Reads bill against the same monthly budget as writes, so no retries."""
    _, x = _refresh([_row("x-stranded", "X", 96, 0)])
    assert x == []


def test_normal_window_still_works_for_both():
    th, x = _refresh([_row("th", "Threads", 30, 0), _row("x", "X", 30, 0)])
    assert th == ["th"] and x == ["x"]
