#!/usr/bin/env python3
"""Did the scheduled jobs actually run yesterday?

Every other alarm in this repo watches what the pipeline produced. None of them
watches whether the pipeline ran at all, and those are different failures with
different silences.

A job that fails leaves a red run you can find. A scheduled run that GitHub
never creates leaves nothing — no entry, no log, no notification. GitHub delays
and drops cron-triggered runs under load, more aggressively the more crons a
repository has, and this one has seven. The DM loop is scheduled every 30
minutes and lands roughly hourly; on 2026-08-06 a five-hour runner shortage
cancelled seven runs before they started. Both are invisible from inside the
repository.

    python scripts/job_health.py            # print the report
    python scripts/job_health.py --check    # exit 1 when a workflow is short

Needs a token with `actions: read` in GITHUB_TOKEN — the one Actions injects is
enough. Without it the script says so and exits 0: an unmeasured channel is
never reported as healthy, and never reported as broken either.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = os.getenv("GITHUB_REPOSITORY", "hopakhei/Content_Loop_Agent")
API = "https://api.github.com"

# How many scheduled runs each workflow should produce in a day.
#
# Written out rather than parsed from the cron line, on purpose. A parser would
# read whatever the workflow currently says and agree with it — including the
# day somebody comments out a schedule. These numbers are the intent, and the
# cron is the implementation; the check is only worth running while the two are
# stated separately.
EXPECTED_PER_DAY = {
    "instagram-dm.yml": 48,        # */30 * * * *
    "generate-pending.yml": 2,     # 0 3,15 * * *
    "post.yml": 1,                 # 30 4 * * *
    "carousel-drip.yml": 1,        # 30 4 * * *
    "fetch-backgrounds.yml": 1,    # 40 2 * * *
    "learn.yml": 1,                # 0 18 * * *
    "runway.yml": 1,               # 0 2 * * *
}

# GitHub drops scheduled runs routinely, so demanding the full count would fire
# most days — and an alarm that fires most days is one nobody reads. Half is the
# level where something is actually wrong rather than merely late.
FLOOR_FRACTION = 0.5

WINDOW_HOURS = 24


def floor_for(expected: int) -> int:
    """The smallest run count that is not a problem. Never below 1: a daily job
    that did not run at all is the case this exists to catch."""
    return max(1, math.floor(expected * FLOOR_FRACTION))


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "loop-job-health",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def counts(token: str, now: datetime | None = None) -> dict:
    """{workflow: {"runs": n, "failed": n}} over the last WINDOW_HOURS.

    Only `schedule` runs are counted. A workflow_dispatch triggered by hand is
    not evidence that the cron is firing — counting it would let a manual rerun
    paper over a schedule that has stopped, which is the exact substitution this
    check exists to prevent.
    """
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=WINDOW_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: dict = {}
    for wf in EXPECTED_PER_DAY:
        url = (f"{API}/repos/{REPO}/actions/workflows/{wf}/runs"
               f"?event=schedule&created=>{since}&per_page=100")
        try:
            data = _get(url, token)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            out[wf] = {"runs": None, "failed": None, "error": str(exc)}
            continue
        runs = data.get("workflow_runs", [])
        out[wf] = {
            "runs": len(runs),
            "failed": sum(1 for r in runs if r.get("conclusion") in
                          ("failure", "cancelled", "timed_out", "startup_failure")),
        }
    return out


def short(c: dict) -> list[str]:
    """Workflows below their floor, or where everything that ran came back bad.

    An unreadable workflow is never 'short' — same rule the runway check uses.
    """
    out = []
    for wf, expected in EXPECTED_PER_DAY.items():
        row = c.get(wf) or {}
        n = row.get("runs")
        if n is None:
            continue
        fl = floor_for(expected)
        if n < fl:
            out.append(f"{wf}: {n} scheduled runs in {WINDOW_HOURS}h, expected "
                       f"about {expected} (floor {fl})")
        elif row.get("failed") and row["failed"] == n:
            out.append(f"{wf}: all {n} scheduled runs in {WINDOW_HOURS}h failed")
    return out


def render(c: dict) -> str:
    lines = [f"Scheduled job health — last {WINDOW_HOURS}h",
             f"  {'workflow':26}{'ran':>5}{'expected':>10}{'floor':>7}{'bad':>6}"]
    for wf, expected in EXPECTED_PER_DAY.items():
        row = c.get(wf) or {}
        n, bad = row.get("runs"), row.get("failed")
        n_txt = "n/a" if n is None else str(n)
        bad_txt = "-" if bad is None else str(bad)
        lines.append(f"  {wf:26}{n_txt:>5}{expected:>10}{floor_for(expected):>7}{bad_txt:>6}")
    lines.append(f"  Floor is {int(FLOOR_FRACTION * 100)}% of expected — GitHub drops "
                 "scheduled runs routinely, and a daily nag gets muted.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when a workflow ran fewer times than its floor")
    args = ap.parse_args()

    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        print("GITHUB_TOKEN not set — job health unmeasured, not checked.")
        return

    c = counts(token)
    print(render(c))
    unreadable = [w for w, r in c.items() if r.get("error")]
    if unreadable:
        print(f"\nCould not read: {', '.join(unreadable)}")
    if not args.check:
        return

    problems = short(c)
    if not problems:
        print("\nOK — every scheduled workflow ran at least its floor.")
        return
    print("\nJOBS NOT RUNNING:")
    for p in problems:
        print(f"  - {p}")
    print("\nA missing scheduled run leaves no failed run to find, so this is the "
          "only place it shows up. Check https://www.githubstatus.com first — a "
          "runner shortage looks exactly like this and clears on its own.")
    sys.exit(1)


if __name__ == "__main__":
    main()
